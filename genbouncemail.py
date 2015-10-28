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

from config import ReConfig

instance = "0"

logger = logging.getLogger('genbouncemailhandle')

readdress_configs = ReConfig()
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

#FromEMail = email.utils.formataddr(( 'Re@Address' , 'noreply@readdress.io' ) )

def prepareMail (msg, body=None):
    actual_frommail = msg['From']
    del msg['From']
    del msg['To']

    FromEMail = readdress_configs.get_formatted_noreply()
    msg['To'] = actual_frommail
    msg['From'] = FromEMail

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
    msg.add_header('reply-to', readdress_configs.get_noreply_mailid())

    return actual_frommail

def sendmail( msg, to ):
    key = uuid.uuid4().hex
    rclient.set(key, pickle.dumps((to, msg)))
    rclient.expire(key, readdress_configs.get_sendmail_key_exp_time())
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
    userslist = jsond['userslist']

    subject = msg['Subject']
    del msg['Subject']
    subject = 'Re: ' + subject
    msg['Subject'] = subject

    text = """Your mail could not be sent to these foillowing ids  {} \n 
              Reason : They have deregistered from our services\n""".format(", ".join(userslist))

    recepient = prepareMail (msg, text)

    sendmail(msg, recepient)

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

    handler = ('MAIL-DEREG-HANDLER-['+instance+']')
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
            pickledEv = pickle.dumps(ev)
            genBounceEmail_handler(ev, pickledEv)
        exit()

    genBounceMailHandleBackUp = 'genBounceMailHandle_' + instance
    logger.info("genBounceMailHandleBackUp ListName : {} ".format(genBounceMailHandleBackUp))

    while True:
        for item in ps.listen():
            itype = item['type']
            if itype == 'message':
                del readdress_configs
                readdress_configs = ReConfig()
            else:
                pass
            break

        backupmail = False
        if (rclient.llen(genBounceMailHandleBackUp)):
            evt = rclient.brpop (genBounceMailHandleBackUp)
            backupmail = True
            pickledData = evt[1]
            jsond = pickle.loads(pickledData)
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
