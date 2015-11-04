#! /usr/bin/python3.4

import argparse
import copy
import email.utils
import json
import logging
import logging.handlers
import pickle
import re
import sys
import uuid
from email.utils import parseaddr

from redis import StrictRedis
from validate_email import validate_email

import dbops
import validations
from config import ReConfig

instance = "0"
logger = logging.getLogger('supportChannel')

readdress_configs = ReConfig()

#class for all db operations using mongodb
db = dbops.MongoORM()

#instanttiate class for common validations
valids = validations.Validations()

#below regex objs are for handling new thread mails
taddrcomp = re.compile('([\w.-]+(#)[\w.-]+)@'+readdress_configs.get_ourdomain() )

subcomp = re.compile('#')

rclient = StrictRedis()
ps = rclient.pubsub()
ps.subscribe(['configmodified'])

def newmapaddr(a, n=None, setExpiry=None):
    sendInvite2User = False
    mapped = db.getmapped(a)
    if not mapped:
        ''' better to add ttl for this address '''
        mapped = uuid.uuid4().hex+'@'+readdress_configs.get_ourdomain() 
        db.insertUser( a, mapped, n , setExpiry)
        logger.info('insterted new ext user ' + a + ' -> ' + mapped)
        sendInvite2User = True
    return mapped, sendInvite2User

def populate_from_addresses(msg):
    fromstring = msg['From']
    fromname, fromemail = parseaddr(fromstring)
    fromdomain = valids.getdomain(fromemail)

    if readdress_configs.get_ourdomain()  == fromdomain:
        return False, False

    mapped, sendInvite2User = newmapaddr(fromemail, fromname, True)
    if not mapped:
        return False, sendInvite2User
    del msg['From']

    if not valids.isregistereduser(mapped):
        sendInvite2User = True

    if fromname:
        logger.info("Actual From address {} / {}".format(fromname, fromemail))
        msg['From'] = email.utils.formataddr((fromname, mapped))
    else:
        logger.info("Actual From address {}".format(fromemail))
        msg['From'] = mapped
    logger.info('From: ' + str(msg['From']))
    return True, sendInvite2User

def sendInvite (invitesrcpts, fromname):
    logger.info("Sending invites from {} to {}".format(fromname, ','.join(invitesrcpts)))
    if fromname is None:
        fromname = ""
    for mailid in invitesrcpts:
        if valids.isregistereduser(mailid):
            user = db.findInviteUsers ( mailid )
            if not user:
                user =  db.insertIntoInviteRecipients (mailid)
                msg = {'template_name': 'readdressInvite', 'email': mailid,
                    'global_merge_vars': [{'name': 'friend', 'content': fromname}]}
                rclient.publish('mailer',pickle.dumps(msg))

def getToAddresses(msg):
    torecipients = list()
    invitercpts = list()
    tostring = msg.get('To')
    if tostring is None:
        return torecipients, invitercpts, list()
    tolst = tostring.split(',')
    tolst = [to.strip() for to in tolst if not 'undisclosed-recipient' in to]
    actualTo = list()
    for toaddr in tolst:
        toname, to  = parseaddr(toaddr)
        actualTo.append(to)
        if toname is None:
            toname = valids.getuserid(to)
        elif validate_email(toname):
            toname = valids.getuserid(to)
        logger.info("NAME : {} ".format(toname))

        mto = taddrcomp.match(to)

        if mto is not None:
            maddress = subcomp.sub('@', mto.group(1), count=1)
            if maddress is not None and validate_email(maddress):
                mapped = db.getmapped(maddress)
                if not mapped:
                    invitercpts.append(maddress)
                newmapaddr(maddress, toname, True)
                logger.info("changed address is : {} , {}".format(maddress,toname))
                modto = [maddress, toname]
        else:
            mapped = db.getmapped(to)
            if not mapped:
                invitercpts.append(to)
                mapped, sendInvite = newmapaddr(to, toname, True)
                modto = [mapped, toname]
            else:
                modto = [mapped, toname]

        torecipients.append( modto )
    return torecipients, invitercpts, actualTo

def validthread(msg):
    msgId = msg.get("Message-ID")
    if msgId is None:
        logger.info("Message-ID not found in mail")
        return False

    msgId = msgId.strip()

    inreplyto = msg.get("In-Reply-To")
    if inreplyto is not None:
        inreplyto = inreplyto.strip()

    ''' References are seperated by '\n\t' oldest thread id being the first id in references '''
    references = msg.get('References')
    if references is not None:
        references = references.strip()

    mailthread = db.findThread ( msgId )
    if mailthread is None:
        ''' no mail with msgId found in DB .. insert new entry in the db'''
        db.insertThread(msgId)
        logger.info("Inserting new doc {}".format(msgId))
        return True
    else:
        logger.info("Possible Duplicate mail {}".format(msgId))
        return False

def isUserEmailTaggedForLI(a):
    """ Check if the user address is tagged for LI """
    user = db.getuser(a)
    if user and 'tagged' in user:
        return user['tagged']
    return None

def mapaddrlist(li):
    rli = []
    logger.info('mapaddrlist li ' + str(li))
    for x in li:
        mapped = db.getmapped(x[0])
        if not mapped:
            continue
        if x[1]:
            rli.append(email.utils.formataddr((x[1],mapped)))
        else:
            rli.append(mapped)
    logger.info('mapaddrlist rli ' + str(rli))
    return rli

def sendmail( evKey, msg, to ):
    key = uuid.uuid4().hex + ',' + evKey
    rclient.set(key, pickle.dumps((to, msg)))
    rclient.expire(key, readdress_configs.get_sendmail_key_exp_time())
    ''' mark key to exipre after 15 secs'''
    msg = None
    key = key.encode()
    rclient.lpush('sendmail', key)
    logger.info("sendmail key {}".format(key))
    return


def supportMailHandler(ev, pickledEv):
    emaildump = (ev['msg']['raw_msg'])
    origmsg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    msg = copy.deepcopy(origmsg)
    del msg['DKIM-Signature']
    del msg['Received']
    if msg.get('X-Originating-Email'):
        del msg['X-Originating-Email']

    fromstring = msg['From']
    fromname, fromemail = parseaddr(fromstring)
    fromdomain = valids.getdomain(fromemail)
    if readdress_configs.get_ourdomain()  == fromdomain:
        logger.info('Received mail from our doamin ... cannot proceed\n')
        return origmsg, msg

    if (fromemail == readdress_configs.ConfigSectionMap('SUPPORT')['SUPPORT_MAIL'] or
       fromemail == readdress_configs.ConfigSectionMap('FEEDBACK')['FEEDBACK_MAIL'] or
       fromemail == readdress_configs.ConfigSectionMap('CONTACT')['CONTACT_MAIL']):
        pass
    else:
        success, sendInvite2User = populate_from_addresses(msg)
        if not success:
            logger.info('Error adding from address')
            return origmsg, msg

        taggedList = []
        if isUserEmailTaggedForLI(fromemail):
            taggedList.append(fromemail)

        # check for Law Interception for all mails 
        if len(taggedList):
            item = []
            item.append(','.join(taggedList))
            item.append(ev)
            rclient.lpush('liarchive', pickle.dumps(item))

    success = validthread(msg)
    if not success:
        logger.info("Not a valid mail thread!!, dropping...")
        return origmsg, msg

    ''' msg will have Message-ID In-ReplyTo and References '''
    evKey =  uuid.uuid4().hex
    rclient.set(evKey, pickledEv)
    ''' mark key to exipre after REDIS_MAIL_DUMP_EXPIRY_TIME secs '''
    ''' Assuming all mail clients to sendmail witn in REDIS_MAIL_DUMP_EXPIRY_TIME '''
    rclient.expire(evKey, readdress_configs.get_redis_mail_dump_exp_time() )
    toaddr = msg['To'] 
    del msg['To'] 
    toname, to  = parseaddr(toaddr)
    if 'support' in  to:
        fwdtomailid = readdress_configs.ConfigSectionMap('SUPPORT')['SUPPORT_MAIL']
        msg['To'] = readdress_configs.ConfigSectionMap('SUPPORT')['SUPPORT_MAIL_MAP']
        recepient = fwdtomailid
        logger.info("mail received to support id, forwarding to {}".format(fwdtomailid))
    elif 'feedback' in to:
        fwdtomailid = readdress_configs.ConfigSectionMap('FEEDBACK')['FEEDBACK_MAIL']
        msg['To'] = readdress_configs.ConfigSectionMap('FEEDBACK')['FEEDBACK_MAIL_MAP']
        recepient = fwdtomailid
        logger.info("mail received to feedback id, forwarding to {}".format(fwdtomailid))
    elif 'contact' in to:
        fwdtomailid = readdress_configs.ConfigSectionMap('CONTACT')['CONTACT_MAIL']
        msg['To'] = readdress_configs.ConfigSectionMap('CONTACT')['CONTACT_MAIL_MAP']
        recepient = fwdtomailid
        logger.info("mail received to contact id, forwarding to {}".format(fwdtomailid))
    else:
        #Need to improve this logic
        logger.info("Could be reply path from support mails")
        frommail = readdress_configs.get_formatted_noreply()
        del msg['From']
        msg['From'] = frommail
        dbuser =  db.getuser(to)
        if not dbuser:
            logger.info("To Address not found in users db cannot proceed\n")
            return origmsg, msg
        msg['To'] = email.utils.formataddr( ( dbuser['name'], dbuser['actual']) )
        recepient = dbuser['actual']
        
    logger.info("Pushing msg to sendmail list {}\n".format(recepient))
    #below check is to prevent sending mail to self readdress ... 
    sendmail(evKey, msg, recepient)

    return origmsg, msg

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SupportEmailHandler .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    parser.add_argument( '-d', '--debug', help='email dump file', required=False)

    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    handler='SUPPORT-MAILHANDLER-['+instance+']'
    formatter = ('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)

    debugfile = ''
    if 'debug' in argsdict and argsdict['debug'] is not None:
        debugfile = argsdict['debug']
        print(debugfile)
        with open(debugfile, 'r') as f:
            records = json.load(f)
            ev = records[0]
            f.close()
            pickledEv = pickle.dumps(ev)
            supportMailHandler(ev, pickledEv)
        exit()


    supportChannelBackUp = 'supportChannelBackUp_' + instance
    logger.info("supportChannelBackUp ListName : {} ".format(supportChannelBackUp))

    while True:
        #Read config changes only while processing the mesage
        readdress_configs = ReConfig()
        valids.re_readconfig()

        backupmail = False
        if (rclient.llen(supportChannelBackUp)):
            evt = rclient.brpop (supportChannelBackUp)
            backupmail = True
            ev = pickle.loads(evt[1])
            #pickledEv = pickle.dumps(ev)
            pickledEv = evt[1]
            logger.info("Getting events from {}".format(supportChannelBackUp))
        else:
            pickledEv = rclient.brpoplpush('supportChannel', supportChannelBackUp)
            ev = pickle.loads(pickledEv)
            logger.info("Getting events from {}".format('supportChannel'))

        #mail handler
        origmsg, msg = supportMailHandler(ev, pickledEv)
        del origmsg
        del msg

        if(not backupmail):
            logger.info('len of {} is : {}'.format(
                supportChannelBackUp, rclient.llen(supportChannelBackUp)))
            rclient.lrem(supportChannelBackUp, 0, pickledEv)
            logger.info ('len of {} is : {}'.format(supportChannelBackUp, rclient.llen(supportChannelBackUp)))
