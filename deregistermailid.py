#! /usr/bin/python3.4

import argparse
import email.utils
import json
import logging
import logging.handlers
import pickle
import sys
import uuid
from email.mime.text import MIMEText
from email.utils import parseaddr

from redis import StrictRedis
import dbops
import validations 

import phonenumbers

FILESIZE=1024*1024*1024 #1MB
instance = "0"

logger = logging.getLogger('maildereghandle')

#class for all db operations using mongodb
db = dbops.MongoORM()

#instanttiate class for common validations
valids = validations.Validations()


OUR_DOMAIN = 'readdress.io'

rclient = StrictRedis()

REDIS_MAIL_DUMP_EXPIRY_TIME = 15*60
SENDMAIL_KEY_EXPIRE_TIME = 10 * 60

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
    rclient.expire(evKey, REDIS_MAIL_DUMP_EXPIRY_TIME)

    return evKey, frommail

def sendmail( evKey, msg, to ):
    key = uuid.uuid4().hex + ',' + evKey
    rclient.set(key, pickle.dumps((to, msg)))
    rclient.expire(key, SENDMAIL_KEY_EXPIRE_TIME)
    msg = None
    ''' mark key to exipre after 15 secs'''
    key = key.encode()
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


    duser = db.findDeregistedUser( from_email )
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

    user = db.getuser(from_email)

    phoneuser = db.getuser(phonenum[1:]+'@'+OUR_DOMAIN)
    if not user or not phoneuser:
        text = "Phone number given is not registered with us, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not db.isregistereduser(user['mapped']):
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

    db.updateExpAndInsertDeregUser( user )

    del msg
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DeRegEmailHandler .')
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
