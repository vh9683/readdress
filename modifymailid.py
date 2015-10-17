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

from redis import StrictRedis

import dbops
import validations
from  validations import phoneValidations

FILESIZE=1024*1024*1024 #1MB
instance = "0"

logger = logging.getLogger('mailmodifyhandle')

OUR_DOMAIN = 'readdress.io'

rclient = StrictRedis()

db = dbops.MongoORM()

valids = validations.Validations()

REDIS_MAIL_DUMP_EXPIRY_TIME = 10*60
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

    del msg['To']

    msg['To'] = frommail
    msg['From'] = 'noreply@readdress.io'

    #fromname, fromemail = parseaddr(tomail)
    ev['msg']['from_email'] = 'noreply@readdress.io'

    logger.info ("From mail : {} ".format(msg['From']))
    logger.info ("To mail : {} ".format(msg['To']))
    logger.info ("from_email mail : {} ".format(ev['msg']['from_email']))

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
    evKey =  uuid.uuid4().hex
    rclient.delete(evKey)
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

def emailModifyHandler(ev, pickledEv):
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
    csvphonenum = ev['msg']['subject']

    oldphonenum = csvphonenum.split(',')[0].strip()

    newphonenum = csvphonenum.split(',')[1].strip()

    user = db.getuser(from_email)

    duser = db.findDeregistedUser( from_email  )
    if duser:
        text = "Phone number is already de-registered with us."
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    phvalids = phoneValidations(oldphonenum)
    if not phvalids.validate():
        logger.info ("Exception raised {}".format(phvalids.get_result()))
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not phvalids.is_number_valid():
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not phvalids.is_allowed_MCC():
        text = " This Service is not available in your Country as of now. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    del phvalids
    phvalids = None

    logger.info ("USER {}".format(user))
    logger.info( "OLD PHONE NUM : {} ".format(oldphonenum[1:]+'@'+OUR_DOMAIN) )
    oldphoneuser = db.getuser(oldphonenum[1:]+'@'+OUR_DOMAIN)
    logger.info("oldphoneuser {}".format(oldphoneuser))
    if not user or not oldphoneuser:
        text = "Old Phone number given is not registered with us, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not valids.isregistereduser(user['mapped']):
        text = "Old Phone number given is not valid, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if user['actual'] != from_email or user['mapped'] != (oldphonenum[1:]+'@'+OUR_DOMAIN):
        text = " Your email id and old phone number does not match, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if user['mapped'] != oldphoneuser['mapped']:
        text = "You are not allowed to change this phone number, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    phvalids = phoneValidations(newphonenum)
    if not phvalids.validate():
        logger.info ("Exception raised {}".format(phvalids.get_result()))
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not phvalids.is_number_valid():
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    if not phvalids.is_allowed_MCC():
        text = " This Service is not available in your Country as of now. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True

    newphoneuser = db.getuser(newphonenum[1:]+'@'+OUR_DOMAIN)
    if newphoneuser and valids.isregistereduser(newphoneuser['mapped']):
        text = "New Phone number given is already registered with us, please check and retry. \n "
        evKey, recepient = prepareMail (ev, msg, text)
        sendmail(evKey, msg, recepient)
        return True
    
    db.updateMapped (user['actual'], (newphonenum[1:]+'@'+OUR_DOMAIN))
    
    # add modification collections ... its needed for premium customers

    text = "Your alias is changed to {}\n".format(newphonenum[1:]+'@'+OUR_DOMAIN)

    evKey, recepient = prepareMail (ev, msg, text)

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
            emailModifyHandler(ev, pickledEv)
        exit()

    formatter = logging.Formatter('MAIL-DEREG-HANDLER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
    hdlr = logging.handlers.RotatingFileHandler('/var/tmp/mailmodifyhandle'+instance+'.log', maxBytes=FILESIZE, backupCount=10)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

    mailModifyhandlerBackUp = 'mailModifyhandler_' + instance
    logger.info("mailModifyhandlerBackUp ListName : {} ".format(mailModifyhandlerBackUp))

    while True:
        backupmail = False
        if (rclient.llen(mailModifyhandlerBackUp)):
            evt = rclient.brpop (mailModifyhandlerBackUp)
            backupmail = True
            ev = pickle.loads(evt[1])
            pickledEv = pickle.dumps(ev)
            logger.info("Getting events from {}".format(mailModifyhandlerBackUp))
        else:
            pickledEv = rclient.brpoplpush('mailModifyhandler', mailModifyhandlerBackUp)
            ev = pickle.loads(pickledEv)
            logger.info("Getting events from {}".format('mailModifyhandler'))

        #mail handler
        emailModifyHandler(ev, pickledEv)

        if(not backupmail):
            logger.info('len of {} is : {}'.format(
                mailModifyhandlerBackUp, rclient.llen(mailModifyhandlerBackUp)))
            rclient.lrem(mailModifyhandlerBackUp, 0, pickledEv)
            logger.info ('len of {} is : {}'.format(mailModifyhandlerBackUp, rclient.llen(mailModifyhandlerBackUp)))
