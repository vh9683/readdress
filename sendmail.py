#! /usr/bin/python3.4

from redis import StrictRedis
import pickle
import logging
import logging.handlers
import smtplib
import argparse
import logging
import logging.handlers
import sys
from email.utils import parseaddr


'''
-------------
Level   Value
-------------
CRITICAL    50
ERROR   40
WARNING 30
INFO    20
DEBUG   10
UNSET   0
'''

FILESIZE=1024*1024*1024 #1MB

def sendmail(msg, to, logger):
    ''' function to be optimised '''
    #server = smtplib.SMTP('smtp.mandrillapp.com', 587)
    server = smtplib.SMTP('localhost', 587)
    try:
        #server.set_debuglevel(True)

        # identify ourselves, prompting server for supported features
        server.ehlo()

        # If we can encrypt this session, do it
        #if server.has_extn('STARTTLS'):
        #    server.starttls()
        #    server.ehlo() # re-identify ourselves over TLS connection
        #    server.login('vidyartibng@gmail.com', 'c3JOgoZZ9BmKN4swnnBEpQ')

        logger.info('RCPT : {}'.format(to))
        fromstring = msg['From']
        fromname, fromemail = parseaddr(fromstring)
        logger.info('SENDER : {}'.format(fromemail))

        composed = msg.as_string()
        logger.debug('Actual Msg : {}'.format(composed))
        server.sendmail(fromemail, to, composed)
    finally:
        server.quit()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='MailSender .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    FILESIZE=1024*1024*1024 #1MB

    handler =('MailSender-['+instance+']')
    formatter=('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
    logger = logging.getLogger('mailHandler'+instance)

    rclient = StrictRedis()

    sendmailbackup = 'sendmailbackup_'+instance
    while True:
        backmail = False
        if (rclient.llen(sendmailbackup)):
            tupitem = rclient.brpop (sendmailbackup)
            logger.info("Getting Mails from {}".format(sendmailbackup))
            backmail = True
            item = (tupitem[1]).decode()
        else:
            item = rclient.brpoplpush('sendmail', sendmailbackup)
            logger.info("Getting Mails from {}".format('sendmail'))
            item = item.decode()

        #Get the smtp msg from redis
        logger.info("Item : {}".format(item))
        msgtuplepickle = rclient.get(item)
        if msgtuplepickle:
            msgtuple = pickle.loads(msgtuplepickle)
            #Get the inbound json obj from redis
            logger.info('item is {} '.format(item))
            keys = item.split(',')
            sendmail(msgtuple[1], msgtuple[0], logger)

            if len(keys) == 2:
                evKey = keys[1]
                if evKey and rclient.exists(evKey):
                    rclient.delete(evKey)

            rclient.delete(item)
        else:
            pass
        #No need to remove from redis .. it will be removed after expiry
        if(backmail == False):
            logger.info('len of {} is : {}'.format(sendmailbackup, rclient.llen(sendmailbackup)))
            rclient.lrem(sendmailbackup, 0, item)
            logger.info('len of {} is : {}'.format(sendmailbackup, rclient.llen(sendmailbackup)))
