#! /usr/bin/python3.4

import argparse
import copy
import datetime
import email.utils
import json
import logging
import logging.handlers
import pickle
import re
import sys
import uuid
from email.utils import parseaddr

import pymongo
from redis import StrictRedis
from validate_email import validate_email

FILESIZE=1024*1024*1024 #1MB
instance = "0"
try:
    conn=pymongo.MongoClient()
    print ("Connected successfully!!!")
except pymongo.errors.ConnectionFailure as e:
    print ("Could not connect to MongoDB: %s" % e )

logger = logging.getLogger('mailHandler')

OUR_DOMAIN = 'readdress.io'

db = conn.inbounddb
#Set expiry after 24 hours
db.threadMapper.ensure_index("Expiry_date", expireAfterSeconds=24*60*60)

#TTL for invites users .. expiry after 5 mins
db.users.ensure_index("Expiry_date", expireAfterSeconds=24*60*60)

#expire after 30days from now
db.invitesRecipients.ensure_index("Expiry_date", expireAfterSeconds=0)

#below regex objs are for handling new thread mails
taddrcomp = re.compile('([\w.-]+(__)[\w.-]+)@'+OUR_DOMAIN)

subcomp = re.compile('__')

rclient = StrictRedis()


REDIS_MAIL_DUMP_EXPIRY_TIME = 10*60

def getdomain(a):
    return a.split('@')[-1]

def getuserid(a):
    return a.split('@')[0]

def isourdomain( a):
    return getdomain(a) == OUR_DOMAIN

def isknowndomain(a):
    if isourdomain(a):
        return True
    known = db.domains.find_one({'domain': getdomain(a)})
    if not known:
        return False
    return True

def getuser(a):
    if isourdomain(a):
        user = db.users.find_one({'mapped': a})
    else:
        user = db.users.find_one({'actual': a})
    return user

def insertUser(a, m, n=None, setExpiry = False):
    user = getuser(a)
    if user:
        return True

    if setExpiry:
        utc_timestamp = datetime.datetime.utcnow()
        if n:
            db.users.insert( {'mapped': m, 'actual': a, 'name' : n, 'Expiry_date' : utc_timestamp} )
        else:
            db.users.insert( { 'mapped': m, 'actual': a, 'Expiry_date': utc_timestamp } )
    else:
        if n:
            db.users.insert( {'mapped': m, 'actual': a, 'name' : n} )
        else:
            db.users.insert( { 'mapped': m, 'actual': a } )

    return True

def getmapped(a):
    user = getuser(a)
    if not user:
        return None
    return user['mapped']

def newmapaddr(a, n=None, setExpiry=None):
    sendInvite2User = False
    mapped = getmapped(a)
    if not mapped:
        ''' better to add ttl for this address '''
        mapped = uuid.uuid4().hex+'@'+OUR_DOMAIN
        insertUser( a, mapped, n , setExpiry)
        logger.info('insterted new ext user ' + a + ' -> ' + mapped)
        sendInvite2User = True
    return mapped, sendInvite2User

def populate_from_addresses(msg):
    fromstring = msg['From']
    fromname, fromemail = parseaddr(fromstring)
    mapped, sendInvite2User = newmapaddr(fromemail, fromname, True)
    if not mapped:
        return False, sendInvite2User
    del msg['From']

    if not isregistereduser(mapped):
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
        user = db.invitesRecipients.find_one( { 'email' : mailid } )
        if not user:
            utc_timestamp = datetime.datetime.utcnow() + datetime.timedelta(days=30)
            user = db.invitesRecipients.insert( { 'email' : mailid, 'Expiry_date' : utc_timestamp } )
            msg = {'template_name': 'readdressInvite', 'email': mailid, 'global_merge_vars': [{'name': 'friend', 'content': fromname}]}
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
        toname,to  = parseaddr(toaddr)
        actualTo.append(to)
        if toname is None:
            toname = getuserid(to)
        elif validate_email(toname):
            toname = getuserid(to)
        logger.info("NAME : {} ".format(toname))

        mto = taddrcomp.match(to)
        if mto is not None:
            maddress = subcomp.sub('@', mto.group(1), count=1)
            if maddress is not None:
                mapped = getmapped(maddress)
                if not mapped:
                    invitercpts.append(maddress)
                newmapaddr(maddress, toname, True)
                logger.info("changed address is : {} , {}".format(maddress,toname))
                to = [maddress, toname]
        else:
            mapped = getmapped(to)
            if not mapped:
                invitercpts.append(to)
                mapped, sendInvite = newmapaddr(to, toname, True)
                to = [mapped, toname]
            else:
                to = [mapped, toname]

            logger.info ("To addrs {}".format(to))
        logger.info("Toname is : {}".format(toname))

        torecipients.append( to )
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
            ccname = getuserid(cc)
        elif validate_email(ccname):
            ccname = getuserid(cc)

        mcc = taddrcomp.match(cc)
        if mcc is not None:
            maddress = subcomp.sub('@', mcc.group(1), count=1)
            if maddress is not None:
                mapped = getmapped(maddress)
                if not mapped:
                    invitercpts.append(maddress)
                newmapaddr(maddress, ccname, True)
                logger.info("Mapped address is : {}".format(maddress))
                cc = [maddress, ccname]
        else:
            cc = [cc, ccname]
            mapped = getmapped(cc)
            if not mapped:
                invitercpts.append(cc)
                mapped, sendInvite = newmapaddr(cc, ccname, True)
                cc = [mapped, ccname]
            else:
                cc = [mapped, ccname]

            logger.info ("cc addrs {}".format(cc))
        logger.info("ccname is : {}".format(ccname))

        ccrecipients.append(cc)
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

def valid_uuid4(a):
    userid = getuserid(a)
    try:
        val = uuid.UUID(userid, version=4)
    except ValueError:
        # If it's a value error, then the string 
        # is not a valid hex code for a UUID.
        return False

    # If the uuid_string is a valid hex code, 
    # but an invalid uuid4,
    # the UUID.__init__ will convert it to a 
    # valid uuid4. This is bad for validation purposes.
    return val.hex == userid

def isregistereduser(a):
    """ check whether the user address is a registered one or generated one """
    return not valid_uuid4(a)

def valid_email_addresses (msg,allrecipients,from_email):
    for id,name in allrecipients:
        success = isregistereduser(id)
        if success:
            return True
    success =  getuser(from_email)
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

    timestamp = datetime.datetime.now()
    utc_timestamp = datetime.datetime.utcnow()

    mailthread = db.threadMapper.find_one( { 'threadId' : msgId } )
    if mailthread is None:
        ''' no mail with msgId found in DB .. insert new entry in the db'''
        if references is None:
            db.threadMapper.insert( { 'threadId' : msgId , "date": timestamp, "Expiry_date" : utc_timestamp} )
            logger.info("Inserting new doc {}".format(msgId))
        else:
            db.threadMapper.insert( { 'threadId' : msgId, 'references' : references,
                                    "date": timestamp, "Expiry_date" : utc_timestamp} )
            logger.info("Inserting new doc {}".format(msgId))
        return True
    else:
        logger.info("Possible Duplicate mail {}".format(msgId))
        return False

def isUserEmailTaggedForLI(a):
    """ Check if the user address is tagged for LI """
    user = getuser(a)
    if user and 'tagged' in user:
        return user['tagged']
    return None

def getactual(a):
    user = getuser(a)
    if not user:
        return None
    return user['actual']


def mapaddrlist(li):
    rli = []
    logger.info('mapaddrlist li ' + str(li))
    for x in li:
        mapped = getmapped(x[0])
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
    ''' mark key to exipre after 15 secs'''
    msg = None
    key = key.encode()
    #rclient.expire(key, 5*60)
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
        user = getmapped(mailid[0])
        if user:
            if not isregistereduser(user):
                totalinvitercpts.append(mailid[0])
        else:
            totalinvitercpts.append(mailid[0])

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
    #rclient.set(evKey, pickle.dumps(ev))
    rclient.set(evKey, pickledEv)
    ''' mark key to exipre after REDIS_MAIL_DUMP_EXPIRY_TIME secs '''
    ''' Assuming all mail clients to sendmail witn in REDIS_MAIL_DUMP_EXPIRY_TIME '''
    #rclient.expire(evKey, REDIS_MAIL_DUMP_EXPIRY_TIME)
    logger.info("All recipients {}".format(allrecipients))
    for mailid in allrecipients:
        rmailid = ""
        if not isourdomain(mailid[0]):
            continue
        rto = mapaddrlist(allrecipients)
        actual = getactual(mailid[0])
        if not actual:
            continue
        if mailid[1]:
            rmailid = actual
            recepient = email.utils.formataddr((mailid[1],actual))
            tremove = email.utils.formataddr((mailid[1],mailid[0]))
        else:
            rmailid = actual
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
        logger.info('To: ' + str(rto))
        msg['To'] = ','.join(rto)
        logger.info("Pushing msg to sendmail list {}\n".format(recepient))

        #below check is to prevent sending mail to self readdress ... 
        if ev['msg']['from_email'] != getactual(mailid[0]):
            sendmail(evKey, msg, recepient)


    sendInvite(totalinvitercpts, fromname)
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

    debugfile = ''
    if 'debug' in argsdict and argsdict['debug'] is not None:
        debugfile = argsdict['debug']
        print(debugfile)
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

        with open(debugfile, 'r') as f:
            records = json.load(f)
            ev = records[0]
            f.close()
            pickledEv = pickle.dumps(ev)
            emailHandler(ev, pickledEv)
        exit()

    formatter = logging.Formatter('MAILHANDLER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
    hdlr = logging.handlers.RotatingFileHandler('/var/tmp/mailhandler_'+instance+'.log', maxBytes=FILESIZE, backupCount=10)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

    mailhandlerBackUp = 'mailhandlerBackUp_' + instance
    logger.info("MailHandlerBackUp ListName : {} ".format(mailhandlerBackUp))

    while True:
        backupmail = False
        if (rclient.llen(mailhandlerBackUp)):
            evt = rclient.brpop (mailhandlerBackUp)
            backupmail = True
            ev = pickle.loads(evt[1])
            pickledEv = pickle.dumps(ev)
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
