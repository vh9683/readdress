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
from config import ReConfig

import dbops
import validations

instance = "0"
logger = logging.getLogger('mailHandler')

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


def sendBounceMail (evKey, origmail, userslist):
    logger.info("Sending bounce mails to originator for following mails :{}".format(userslist))
    data = dict()
    data['evkey'] = evKey
    data['origmail'] = origmail
    data['userslist'] = userslist

    rclient.lpush('genBounceMailHandle', pickle.dumps( convertDictToJson(data) ) )
    del data
    return


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

def getCcAddresses(msg):
    ccrecipients = list()
    invitercpts = list()
    ccstring = msg.get('Cc')
    if ccstring is None:
        return ccrecipients, invitercpts, list()
    cclst = ccstring.split(',')
    cclst = [cc.strip() for cc in cclst if not 'undisclosed-recipient' in cc]
    actualCc = list()
    for ccaddr in cclst:
        ccname, cc = parseaddr( ccaddr )
        actualCc.append(cc)

        if ccname is None:
            ccname = valids.getuserid(cc)
        elif validate_email(ccname):
            ccname = valids.getuserid(cc)

        mcc = taddrcomp.match(cc)
        if mcc is not None:
            maddress = subcomp.sub('@', mcc.group(1), count=1)
            if maddress is not None:
                mapped = db.getmapped(maddress)
                if not mapped:
                    invitercpts.append(maddress)
                newmapaddr(maddress, ccname, True)
                logger.info("Mapped address is : {}".format(maddress))
                modcc = [maddress, ccname]
        else:
            #cc = [cc, ccname]
            mapped = db.getmapped(cc)
            if not mapped:
                invitercpts.append(cc)
                mapped, sendInvite = newmapaddr(cc, ccname, True)
                modcc = [mapped, ccname]
            else:
                modcc = [mapped, ccname]

        ccrecipients.append(modcc)
    return ccrecipients, invitercpts, actualCc


def checkForBccmail (msg):
    receivedhrds = msg.get_all('Received')
    bccinmail = False
    bccemail = []
    for hdr in receivedhrds:
        logger.info("Received header \n {}".format(hdr))
        match = re.search('([\w.-]+)@([\w.-]+)', hdr)
        if match is not None:
            mailaddr = match.group()
            bccinmail = True
            bccemail.append(mailaddr)

    if bccinmail:
        logger.info('Mail contains BCC email addresses in Received Header... Dropping Mail')
        logger.info("Bcc Emails Addresses are : {}".format( ', '.join(bccemail)))

    return bccinmail


def valid_email_addresses (msg,allrecipients,from_email):
    for id,name in allrecipients:
        success = valids.isregistereduser(id)
        if success:
            return True
    success =  db.getuser(from_email)
    if success:
        return True
    return False


def validthread(msg,allrecipients,from_email):
    """ 
      Every new thread must come from known domain and
      and very mail must have at least one regiestered user
      who can be the sender or recepient
  """
    ''' A useful thread identification algorithm is explained in 
      http://www.jwz.org/doc/threading.html ...
      
      NOTES:
            References header: will contains list of all message id's for tentire converstion.
            Oldest MsgId being the first. Header contain a list of Message-IDs listing the parent, grandparent, great-grandparent, 
            and so on, of this message, oldest first. 
            That is, the direct parent of this message will be the last element of the References header.
            NewsGroups are allowed to truncate the refrences header.

            In-Reply-To Header will (most of times) contain the msgid of recent message for which reply is being sent to.
            
            New Mail will not contein In-ReplyTo and References header. It will contain MsgId header only.


    Design:
        1) For each new mail received we need to store msgId as key and value "" (mails which does not contain In-Reply-To header)
        2) For each reply mail, we need to get the refrences header and in-reply-to id and search in collections for existing entries.
           Get In-Reply-To header mostly contains the msgId of previous mail, search is int the collection and get the actual msgId
           and check if it is the head of references header. If these check passed the thread is valid.
           Now add the nre msgId of reply mail into the values section for the original msgId stored in the mongodb
           Or 
           if in-reply-to value is part of any documents of existing treat this as valid thread and add the msgid of reply mail in to 
            the document.
        3) Handling duplicates, if the msgId of the new reply mail is part of any existing documents of db then treat this mail as 
        duplicate. We need not handle this mail.

        For above logic we may think of adding subject as well. for all reply mails we can match the existing subject line excluding "re:" 
        charactes of the reply mail subject line.

    Notes:
     1) For new mails the existing gmail , other mail servers does not produce multiple inbound triggers for mail id's in cc header.
     2) But for reply path the gmail and other servers does produce multiple inbound triggers (possibly with same msgId) for each
     mail id in cc header.

  '''

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

"""
    'fa' --> actual from header
    'fm' --> modified from header
    'ta' --> actual to addresses
    'ca' --> actual cc addresses
    's' --> subject
    'd' --> date
    'msgid' --> actual msgid
    'li' --> Boolean Tagged to LI ?
    'acount' --> attachments count
"""

def convertDictToJson(data):
    json_data = json.dumps(data)
    return json_data

def addModifiedCcs (data, cc):
    if len(cc) > 0:
        ccs = [ id for id,name in cc ]
        data['cm'] = ','.join(ccs)

def addModifiedTos (data, to):
    if len(to) > 0:
        tos = [ id for id,name in to ]
        data['tm'] = ','.join(tos)

def constructJsonForArchive (ev, msg, origmsg, actualTos, actualCcs):
    data = dict()
    data['fa'] = origmsg['From']
    data['fm'] = msg['From']
    if actualTos:
        data['ta'] = ','.join(actualTos)
    else:
        data['ta'] = "None"

    if actualCcs:
        data['ca'] = ','.join(actualCcs)
    else:
        data['ca'] = 'None'

    data['s'] = msg['Subject']
    data['d'] = origmsg['Date']
    data['msgid'] = origmsg['Message-ID']

    acount = 0
    keys = [ k for k in ev['msg'] if k in ev['msg'].keys() ]
    if 'attachments' in keys:
        acount += len(ev['msg']['attachments'])
    if 'images' in keys:
        acount += len(ev['msg']['images'])

    data['acount'] = acount

    return data

def emailHandler(ev, pickledEv):
    ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
  '''
    emaildump = (ev['msg']['raw_msg'])
    origmsg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    msg = copy.deepcopy(origmsg)
    del msg['DKIM-Signature']

    '''
  if checkForBccmail(msg):
    #Dropping mail
    continue
  '''

    ''' handle ev msg here 
      1) parse raw msg
      2) check for validity
      3) check if bcc mail and drop the mail / do some thing
      4) move the completed section to other parts such as li / sendmail or some thing else
  '''
    fromstring = msg['From']
    fromname, fromemail = parseaddr(fromstring)
    fromdomain = valids.getdomain(fromemail)
    if readdress_configs.get_ourdomain()  == fromdomain:
        logger.info('Received mail from our doamin ... cannot proceed\n')
        del origmsg
        del msg
        return False


    allrecipients = []
    totalinvitercpts = []
    torecipients, toinvites, actualTos = getToAddresses(msg)
    ccrecipients, ccinvites, actualCcs = getCcAddresses(msg)

    if len(actualTos) == 0:
        actualTos = None
    if len(actualCcs) == 0:
        actualCcs = None

    allrecipients = torecipients + ccrecipients

    totalinvitercpts = toinvites + ccinvites

    for mailid in allrecipients:
        logger.info("for loop mail : {} ".format(mailid))
        if not valids.isregistereduser(mailid[0]):
            user = db.getuser(mailid[0])
            if user:
                totalinvitercpts.append(user['actual'])

    del msg['To']
    del msg['Cc']

    success,sendInvite2User = populate_from_addresses(msg)
    if not success:
        logger.info('Error adding from address')
        del origmsg
        del msg
        return False

    fromemail = ev['msg']['from_email']

    fromname = ev['msg']['from_name']

    if sendInvite2User:
        totalinvitercpts.append(fromemail)

    success = validthread(msg, allrecipients, fromemail)
    if not success:
        logger.info("Not a valid mail thread!!, dropping...")
        del msg
        del origmsg
        return False

    success = valid_email_addresses(msg, allrecipients, fromemail)
    if not success:
        logger.info("Not a valid mail thread!! email address check failed, dropping and notifying sender...")
        msg = {'template_name': 'readdressfailure', 'email': fromemail, 'global_merge_vars': [{'name': 'reason', 'content': "Mail could not be processed as none of the mail-id's are known to us."}]}
        count = rclient.publish('mailer',pickle.dumps(msg))
        logger.info('message ' + str(msg))
        logger.info('message published to ' + str(count))
        del origmsg
        del msg
        return False

    taggedList = []
    logger.info ("All recipients {}".format(allrecipients))
    for mailid,name in allrecipients:
        if isUserEmailTaggedForLI(mailid):
            taggedList.append(mailid)

    if isUserEmailTaggedForLI(fromemail):
        taggedList.append(fromemail)

    # check for Law Interception for all mails 
    if len(taggedList):
        item = []
        item.append(','.join(taggedList))
        item.append(ev)
        rclient.lpush('liarchive', pickle.dumps(item))

    logger.info("sendmail to mailarchive")

    data = constructJsonForArchive ( ev, msg, origmsg, actualTos, actualCcs )
    addModifiedTos(data, torecipients)
    addModifiedCcs(data, ccrecipients)

    if len(taggedList):
        data['li'] = True
    else:
        data['li'] = False

    jsondata = convertDictToJson(data)
    jpickle = pickle.dumps (jsondata)

    rclient.lpush('mailarchive', jpickle)
    logger.info ("Json : {}".format(jsondata))
    del data
    del jpickle


    #msg['X-MC-PreserveRecipients'] = 'true'

    ''' msg will have Message-ID In-ReplyTo and References '''
    evKey =  uuid.uuid4().hex
    rclient.set(evKey, pickledEv)
    ''' mark key to exipre after REDIS_MAIL_DUMP_EXPIRY_TIME secs '''
    ''' Assuming all mail clients to sendmail witn in REDIS_MAIL_DUMP_EXPIRY_TIME '''
    rclient.expire(evKey, readdress_configs.get_redis_mail_dump_exp_time() )
    logger.info("All recipients {}".format(allrecipients))
    deregusers = list()
    for mailid in allrecipients:
        if not valids.isourdomain(mailid[0]):
            continue
        rto = mapaddrlist(allrecipients)
        actual = db.getactual(mailid[0])
        if not actual:
            continue
        if mailid[1]:
            recepient = email.utils.formataddr((mailid[1],actual))
            tremove = email.utils.formataddr((mailid[1],mailid[0]))
        else:
            recepient = actual
            tremove = mailid[0]
        if tremove in rto:
            rto.remove(tremove)
        if msg['From'] in rto:
            rto.remove(msg['From'])
        if 'To' in msg:
            del msg['To']
        if 'Cc' in msg:
            del msg['Cc']
        user = db.getuser(actual)
        if user:
            rto.append(email.utils.formataddr((user['name'],user['actual'])))
        logger.info('To: ' + str(rto))
        msg['To'] = ','.join(rto)
        logger.info("Pushing msg to sendmail list {}\n".format(recepient))

        #below check is to prevent sending mail to self readdress ... 
        if ev['msg']['from_email'] == db.getactual(mailid[0]):
            continue
        elif db.findDeregistedUser(recepient) :
            deregusers.append(recepient)
            continue
        else:
            sendmail(evKey, msg, recepient)

    if len(totalinvitercpts):
        sendInvite(totalinvitercpts, fromname)

    # send bounce mail to originator
    if len(deregusers):
        sendBounceMail (evKey, origmsg, deregusers)

    del origmsg
    del msg
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='EmailHandler .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    parser.add_argument( '-d', '--debug', help='email dump file', required=False)

    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    handler='MAILHANDLER-['+instance+']'
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
            emailHandler(ev, pickledEv)
        exit()


    mailhandlerBackUp = 'mailhandlerBackUp_' + instance
    logger.info("MailHandlerBackUp ListName : {} ".format(mailhandlerBackUp))

    while True:
        #Read config changes only while processing the mesage
        for item in ps.listen():
            itype = item['type']
            if itype == 'message':
                print ('DATA {}'.format(item['data']) )
                del readdress_configs
                print ("REadin configs")
                readdress_configs = ReConfig()
                valids.re_readconfig()
            else:
                pass
            break

        backupmail = False
        if (rclient.llen(mailhandlerBackUp)):
            evt = rclient.brpop (mailhandlerBackUp)
            backupmail = True
            ev = pickle.loads(evt[1])
            #pickledEv = pickle.dumps(ev)
            pickledEv = evt[1]
            logger.info("Getting events from {}".format(mailhandlerBackUp))
        else:
            pickledEv = rclient.brpoplpush('mailhandler', mailhandlerBackUp)
            ev = pickle.loads(pickledEv)
            logger.info("Getting events from {}".format('mailhandler'))

        #mail handler
        emailHandler(ev, pickledEv)

        if(not backupmail):
            logger.info('len of {} is : {}'.format(
                mailhandlerBackUp, rclient.llen(mailhandlerBackUp)))
            rclient.lrem(mailhandlerBackUp, 0, pickledEv)
            logger.info ('len of {} is : {}'.format(mailhandlerBackUp, rclient.llen(mailhandlerBackUp)))

                


