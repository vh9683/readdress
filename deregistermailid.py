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
import phonenumbers
from email.utils import parseaddr
from email.mime.text import MIMEText

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

logger = logging.getLogger('maildereghandle')

OUR_DOMAIN = 'readdress.io'

db = conn.inbounddb
#Set expiry after 24 hours
db.threadMapper.ensure_index("Expiry_date", expireAfterSeconds=24*60*60)

#TTL for invites users .. expiry after 5 mins
db.users.ensure_index("Expiry_date", expireAfterSeconds=24*60*60)

#expire after 30days from now
db.invitesRecipients.ensure_index("Expiry_date", expireAfterSeconds=0)

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


def prepareMail (ev, msg, body=None):
    
    frommail = msg['From']
    del msg['From']

    tomail = msg['To']
    del msg['To']

    msg['To'] = frommail
    msg['From'] = tomail

    fromname, fromemail = parseaddr(tomail)
    ev['msg']['from_email'] = fromemail

    if body:
      textpart = MIMEText(body, 'plain')
      msg.attach(textpart)

    msgId = msg.get('Message-ID')
    msg.add_header("In-Reply-To", msgId)

    pickledEv = pickle.dumps(ev)
    del ev['msg']['raw_msg']
    evKey =  uuid.uuid4().hex
    rclient.set(evKey, pickledEv)

    return evKey, frommail

def sendmail( evKey, msg, to ):
    key = uuid.uuid4().hex + ',' + evKey
    rclient.set(key, pickle.dumps((to, msg)))
    ''' mark key to exipre after 15 secs'''
    key = key.encode()
    #rclient.expire(key, 5*60)
    rclient.lpush('sendmail', key)
    logger.info("sendmail key {}".format(key))
    return

def emailDeregisterHandler(ev, pickledEv):
    ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
    '''
    emaildump = (ev['msg']['raw_msg'])
    gmsg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    del msg['DKIM-Signature']
    del msg['Cc']
    msg['X-MC-PreserveRecipients'] = 'true'
    subject = msg['Subject']
    del msg['Subject'] 
    subject = 'Re: ' + subject
    msg['Subject'] = subject

    from_email = ev['msg']['from_email']
    phonenum = ev['msg']['subject']
    try:
      phonedata = phonenumbers.parse(phonenum,None)
    except phonenumbers.phonenumberutil.NumberParseException as e:
      text = "Invalid phone number given, please check and retry with correct phone number"
      evKey, recepient = prepareMail (ev, msg, text)
      sendmail(evKey, msg, recepient)
      return

    if not phonenumbers.is_possible_number(phonedata) or not phonenumbers.is_valid_number(phonedata):
      text = "Invalid phone number given, please check and retry with correct phone number"
      evKey, recepient = prepareMail (ev, msg, text)
      sendmail(evKey, msg, recepient)
      return

    if phonedata.country_code not in allowedcountries:
      text = "This Service is not available in your Country as of now."
      evKey, recepient = prepareMail (ev, msg, text)
      sendmail(evKey, msg, recepient)
      return

    user = yield self.getuser(from_email)

    phoneuser = yield self.getuser(phonenum[1:]+'@'+OUR_DOMAIN)
    if not user or not phoneuser:
      text = "Phone number given is not registered with us, please check and retry "
      evKey, recepient = prepareMail (ev, msg, text)
      return

    sendmail(evKey, msg, recepient)

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

    formatter = logging.Formatter('MAIL-DEREG-HANDLER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
    hdlr = logging.handlers.RotatingFileHandler('/var/tmp/maildereghandle'+instance+'.log', maxBytes=FILESIZE, backupCount=10)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

    mailDeregisterhandlerBackUp = 'mailDeregisterhandler_' + instance
    logger.info("mailDeregisterhandlerBackUp ListName : {} ".format(mailDeregisterhandlerBackUp))

    while True:
        backupmail = False
        if (rclient.llen(mailDeregisterhandlerBackUp)):
            evt = rclient.brpop (mailDeregisterhandlerBackUp)
            backupmail = True
            ev = pickle.loads(evt[1])
            pickledEv = pickle.dumps(ev)
            logger.info("Getting events from {}".format(mailDeregisterhandlerBackUp))
        else:
            pickledEv = rclient.brpoplpush('mailDeregisterhandler', mailDeregisterhandlerBackUp)
            ev = pickle.loads(pickledEv)
            logger.info("Getting events from {}".format('mailDeregisterhandler'))

        #mail handler
        emailDeregisterHandler(ev, pickledEv)

        if(not backupmail):
            logger.info('len of {} is : {}'.format(
                mailDeregisterhandlerBackUp, rclient.llen(mailDeregisterhandlerBackUp)))
            rclient.lrem(mailDeregisterhandlerBackUp, 0, pickledEv)
            logger.info ('len of {} is : {}'.format(mailDeregisterhandlerBackUp, rclient.llen(mailDeregisterhandlerBackUp)))

