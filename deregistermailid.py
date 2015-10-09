#! /usr/bin/python3.4

import argparse
import datetime
import email.utils
import json
import logging
import logging.handlers
import pickle
import sys
import uuid
from email.mime.text import MIMEText
from email.utils import parseaddr

import pymongo
from redis import StrictRedis

import phonenumbers

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

html = """\
<html>
  <head></head>
  <body>
    <p>Hi!<br>
        &emsp; {}<br>
        Kindly do not reply to this mail. 
        <br>Regards,<br>&emsp;Re@address Team<br>
    </p>
  </body>
</html>
"""

bodypart = """\
    Hi!
      {} 
    Kindly do not reply to this mail. 
    Regards,
      Re@address Team
"""



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

def getuser(a):
    if isourdomain(a):
        user = db.users.find_one({'mapped': a})
    else:
        user = db.users.find_one({'actual': a})
    return user

def getactual(a):
    user = getuser(a)
    if not user:
        return None
    return user['actual']


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
        text = bodypart.format(body)
        textpart = MIMEText(text, 'plain')
        msg.attach(textpart)
        htmlformatted = html.format(body)
        htmlpart = MIMEText(htmlformatted, 'html')
        msg.attach(htmlpart)
 
    msgId = msg.get('Message-ID')
    msg.add_header("In-Reply-To", msgId)
    msg.get('References', msgId)

    msg.add_header('reply-to', 'noreply@readdress.io')

    pickledEv = pickle.dumps(ev)
    del ev['msg']['raw_msg']
    evKey =  uuid.uuid4().hex
    rclient.set(evKey, pickledEv)

    return evKey, frommail

def sendmail( evKey, msg, to ):
    key = uuid.uuid4().hex + ',' + evKey
    rclient.set(key, pickle.dumps((to, msg)))
    msg = None
    ''' mark key to exipre after 15 secs'''
    key = key.encode()
    #rclient.expire(key, 5*60)
    rclient.lpush('sendmail', key)
    logger.info("sendmail key {}".format(key))
    return

allowedcountries = [91,61,1]

def emailDeregisterHandler(ev, pickledEv):
    ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
    '''
    emaildump = (ev['msg']['raw_msg'])
    msg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    del msg['DKIM-Signature']
    del msg['Cc']
    subject = msg['Subject']
    del msg['Subject']
    subject = 'Re: ' + subject
    msg['Subject'] = subject

    from_email = ev['msg']['from_email']
    phonenum = ev['msg']['subject']


    duser = db.deregisteredUsers.find_one ( { 'actual' : from_email } )
    if duser:
        text = "Phone number is already de-registered with us."
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    try:
        phonedata = phonenumbers.parse(phonenum,None)
    except phonenumbers.phonenumberutil.NumberParseException as e:
        logger.info ("Exception raised {}".format(e))
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not phonenumbers.is_possible_number(phonedata) or not phonenumbers.is_valid_number(phonedata):
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if phonedata.country_code not in allowedcountries:
        text = " This Service is not available in your Country as of now. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    user = getuser(from_email)

    phoneuser = getuser(phonenum[1:]+'@'+OUR_DOMAIN)
    if not user or not phoneuser:
        text = "Phone number given is not registered with us, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not isregistereduser(user['mapped']):
        #ignore silently
        return True

    if user['actual'] != from_email or user['mapped'] != (phonenum[1:]+'@'+OUR_DOMAIN):
        text = " You have not registered with this phone number, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True


    text = "Your alias will be unsibscribed in 24 hours. \n"

    evKey, recepient = prepareMail (ev, msg, text)

    sendmail(evKey, msg, recepient)

    utc_timestamp = datetime.datetime.utcnow()

    db.users.update({"actual": user['actual']},
                   {"$set": {'Expiry_date': utc_timestamp}})

    db.deregisteredUsers.insert( user )

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
            emailDeregisterHandler(ev, pickledEv)
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
