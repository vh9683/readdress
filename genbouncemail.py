#! /usr/bin/python3.4

import argparse
import json
import logging
import logging.handlers
import pickle
import sys
import uuid
from email.mime.text import MIMEText

from redis import StrictRedis

FILESIZE=1024*1024*1024 #1MB
instance = "0"

logger = logging.getLogger('genbouncemailhandle')

#class for all db operations using mongodb
#db = dbops.MongoORM()

#instanttiate class for common validations
#valids = validations.Validations()


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

def prepareMail (evKey, msg, body=None):
    frommail = msg['From']
    del msg['From']
    del msg['To']

    msg['To'] = frommail
    fromemail =  'noreply@readdress.io'
    msg['From'] = fromemail

    pickledEv = rclient.get(evKey)
    if not pickledEv:
        raise ValueError("invalid evkey value {}".format( str(evKey)) )

    ev = pickle.loads(pickledEv)
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
    msg.add_header('reply-to', fromemail)

    pickledEv = pickle.dumps(ev)
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


def genBounceEmail_handler(jsond):
    ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
    '''
    msg = jsond['origmail']
    evKey = jsond['evKey']
    userslist = jsond['userslist']

    subject = msg['Subject']
    del msg['Subject']
    subject = 'Re: ' + subject
    msg['Subject'] = subject

    text = """Your mail could not be sent to these foillowing ids  {} \n 
              Reason : They have deregistered from our services\n""".format(", ".join(userslist))

    evKey, recepient = prepareMail (evKey, msg, text)

    sendmail(evKey, msg, recepient)

    del msg
    del jsond

    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='GenBounceMailHandler .')
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
            genBounceEmail_handler(ev, pickledEv)
        exit()

    formatter = logging.Formatter('MAIL-DEREG-HANDLER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
    hdlr = logging.handlers.RotatingFileHandler('/var/tmp/genbouncemailhandle'+instance+'.log', maxBytes=FILESIZE, backupCount=10)
    hdlr.setFormatter(formatter)
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)

    genBounceMailHandleBackUp = 'genBounceMailHandle_' + instance
    logger.info("genBounceMailHandleBackUp ListName : {} ".format(genBounceMailHandleBackUp))

    while True:
        backupmail = False
        if (rclient.llen(genBounceMailHandleBackUp)):
            evt = rclient.brpop (genBounceMailHandleBackUp)
            backupmail = True
            pickledData = evt[1]
            jsond = pickle.loads(pickledData)
            #pickledEv = pickle.dumps(ev)
            logger.info("Getting events from {}".format(genBounceMailHandleBackUp))
        else:
            pickledData = rclient.brpoplpush('genBounceMailHandle', genBounceMailHandleBackUp)
            jsond = pickle.loads(pickledData)
            logger.info("Getting events from {}".format('genBounceMailHandle'))

        #mail handler
        genBounceEmail_handler(jsond)

        if(not backupmail):
            logger.info('len of {} is : {}'.format(
                genBounceMailHandleBackUp, rclient.llen(genBounceMailHandleBackUp)))
            rclient.lrem(genBounceMailHandleBackUp, 0, pickledEv)
            logger.info ('len of {} is : {}'.format(genBounceMailHandleBackUp, rclient.llen(genBounceMailHandleBackUp)))
