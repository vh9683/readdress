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
from config import ReConfig
from validations import PhoneValidations

instance = "0"

logger = logging.getLogger('maildereghandle')

readdress_configs = ReConfig()

#class for all db operations using mongodb
db = dbops.MongoORM()

#instanttiate class for common validations
valids = validations.Validations()

rclient = StrictRedis()

ps = rclient.pubsub()
ps.subscribe(['configmodified'])

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

def prepareMail (msg, body=None):
    actual_frommail = msg['From']
    del msg['From']
    del msg['To']

    FromEMail = readdress_configs.get_formatted_noreply()
    msg['To'] = actual_frommail
    msg['From'] = FromEMail

    if body:
        logger.info("Response : {}".format(body))
        text = bodypart.format(body)
        textpart = MIMEText(text, 'plain')
        msg.attach(textpart)
        htmlformatted = html.format(body)
        htmlpart = MIMEText(htmlformatted, 'html')
        msg.attach(htmlpart)

    msgId = msg.get('Message-ID')
    msg.add_header("In-Reply-To", msgId)
    msg.get('References', msgId)
    msg.add_header('reply-to', readdress_configs.get_noreply_mailid())

    return actual_frommail

def sendmail( msg, to ):
    key = uuid.uuid4().hex
    rclient.set(key, pickle.dumps((to, msg)))
    rclient.expire(key, readdress_configs.get_sendmail_key_exp_time() )
    msg = None
    ''' mark key to exipre after 15 secs'''
    key = key.encode()
    rclient.lpush('sendmail', key)
    logger.info("sendmail key {}".format(key))
    return


def emailDeregisterHandler(ev):
    ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
    '''
    emaildump = (ev['msg']['raw_msg'])
    msg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    del msg['DKIM-Signature']
    del msg['Cc']
    del msg['Received']
    del msg['Message-ID']

    subject = msg['Subject']
    del msg['Subject']
    subject = 'Re: ' + subject
    msg['Subject'] = subject

    from_email = ev['msg']['from_email']
    phonenum = ev['msg']['subject']

    duser = db.findDeregistedUser( from_email )
    if duser:
        text = "Phone number is already de-registered with us."
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True

    suser = db.isUserSuspended( from_email )
    if suser:
        text = "Phone number is already suspended, it will be deregistered, we will be glad to see you back"
        db.updateExpAndInsertDeregUser( suser )
        db.removeSuspendedUser(suser)
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True


    phvalids = PhoneValidations(phonenum)
    if not phvalids.validate():
        logger.info ("Exception raised {}".format(phvalids.get_result()))
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True

    if not phvalids.is_number_valid():
        text = "Invalid phone number given, please check and retry with correct phone number. \n"
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True

    if not phvalids.is_allowed_MCC(db):
        text = " This Service is not available in your Country as of now. \n "
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True

    user = db.getuser(from_email)

    phoneuser = db.getuser(phonenum[1:]+'@'+readdress_configs.get_ourdomain() )
    if not user or not phoneuser:
        text = "Phone number given is not registered with us, please check and retry. \n "
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True

    if not valids.isregistereduser(user['mapped']):
        #ignore silently
        return True

    if user['actual'] != from_email or user['mapped'] != (phonenum[1:]+'@'+readdress_configs.get_ourdomain() ):
        text = " You have not registered with this phone number, please check and retry. \n "
        recepient = prepareMail (msg, text)
        sendmail(msg, recepient)
        return True

    text = "Your alias is deregistered from our service, we wil be glad to see you back. \n"

    recepient = prepareMail (msg, text)

    sendmail(msg, recepient)

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

    handler= ('MAIL-DEREG-HANDLER-['+instance+']')
    formatter=('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)

    debugfile = ''
    if 'debug' in argsdict and argsdict['debug'] is not None:
        debugfile = argsdict['debug']
        print(debugfile)
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

        with open(debugfile, 'r') as f:
            records = json.load(f)
            ev = records[0]
            f.close()
            #pickledEv = pickle.dumps(ev)
            emailDeregisterHandler(ev)
        exit()


    mailDeregisterhandlerBackUp = 'mailDeregisterhandler_' + instance
    logger.info("mailDeregisterhandlerBackUp ListName : {} ".format(mailDeregisterhandlerBackUp))

    while True:
        del readdress_configs
        readdress_configs = ReConfig()
        valids.re_readconfig()

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
        emailDeregisterHandler(ev)

        if(not backupmail):
            logger.info('len of {} is : {}'.format(
                mailDeregisterhandlerBackUp, rclient.llen(mailDeregisterhandlerBackUp)))
            rclient.lrem(mailDeregisterhandlerBackUp, 0, pickledEv)
            logger.info ('len of {} is : {}'.format(mailDeregisterhandlerBackUp, rclient.llen(mailDeregisterhandlerBackUp)))
