#! /usr/bin/python3.4

import argparse
import logging
import logging.handlers
import pickle
import sys
import pystache
import smtplib
from mailtemplates import mailtemplates
from email.mime.text import MIMEText
from redis import StrictRedis

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mailer .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    FILESIZE=1024*1024*1024 #1MB
    handler = ('EMAIL SENDER-['+instance+']')
    formatter = ('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
    logger = logging.getLogger('mailer'+instance)

    rclient = StrictRedis()
    mailerbackup = 'mailer_' + instance

    logger.info("Starting email sender")

    while True:
        if (rclient.llen(mailerbackup)):
            item = rclient.brpop (mailerbackup)
            message = pickle.loads (item[1])
            mailcontent = pystache.render(mailtemplates[message['template_name']]['template'],message['global_merge_vars'])
            msg = msg = MIMEText(mailcontent,'html')
            msg['Subject'] = mailtemplates[message['template_name']]['subject']
            msg['From'] = mailtemplates[message['template_name']]['from_email']
            msg['To'] = message['email']
            s = smtplib.SMTP('localhost')
            s.send_message(msg)
            s.quit()
        else:
            item = rclient.brpoplpush('mailer', mailerbackup)
            message = pickle.loads(item)
            mailcontent = pystache.render(mailtemplates[message['template_name']]['template'],message['global_merge_vars'])
            msg = msg = MIMEText(mailcontent,'html')
            msg['Subject'] = mailtemplates[message['template_name']]['subject']
            msg['From'] = mailtemplates[message['template_name']]['from_email']
            msg['To'] = message['email']
            s = smtplib.SMTP('localhost')
            s.send_message(msg)
            s.quit()
            logger.info ('len of {} is : {}'.format(mailerbackup, rclient.llen(mailerbackup)))
            rclient.lrem(mailerbackup, 0, item)
            logger.info ('len of {} is : {}'.format(mailerbackup, rclient.llen(mailerbackup)))
