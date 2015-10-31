#! /usr/bin/python3.4

import argparse
import logging
import logging.handlers
import pickle
import smtplib
import sys
from email.mime.text import MIMEText

from redis import StrictRedis

import pystache
from config import ReConfig
from mailtemplates import mailtemplates

rclient = StrictRedis()
ps = rclient.pubsub()
ps.subscribe(['configmodified'])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mailer .')
    parser.add_argument('-i','--instance', help='Instance Num of this script ', required=True)
    args = parser.parse_args()
    argsdict = vars(args)
    instance = argsdict['instance']

    handler = ('EMAIL SENDER-['+instance+']')
    formatter = ('\n'+handler+':%(asctime)s-[%(filename)s:%(lineno)s]-%(levelname)s - %(message)s')
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format=formatter)
    logger = logging.getLogger('mailer'+instance)
    readdress_configs = ReConfig()

    mailerbackup = 'mailer_' + instance

    logger.info("Starting email sender")

    while True:
        for item in ps.listen():
            itype = item['type']
            if itype == 'message':
                del readdress_configs
                readdress_configs = ReConfig()
            else:
                pass
            break


        if (rclient.llen(mailerbackup)):
            item = rclient.brpop (mailerbackup)
            message = pickle.loads (item[1])
            mailcontent = pystache.render(mailtemplates[message['template_name']]['template'],message.get('global_merge_vars', ''))
            msg = msg = MIMEText(mailcontent,'html')
            msg['Subject'] = mailtemplates[message['template_name']]['subject']
            From = mailtemplates[message['template_name']]['from_email']
            if From == 'noreply':
                From = readdress_configs.get_formatted_noreply()
            msg['From'] = From
            msg['To'] = message['email']
            s = smtplib.SMTP('localhost')
            s.send_message(msg)
            s.quit()
        else:
            item = rclient.brpoplpush('mailer', mailerbackup)
            message = pickle.loads(item)
            mailcontent = pystache.render(mailtemplates[message['template_name']]['template'],message.get('global_merge_vars', ''))
            msg = msg = MIMEText(mailcontent,'html')
            msg['Subject'] = mailtemplates[message['template_name']]['subject']
            From = mailtemplates[message['template_name']]['from_email']
            if From == 'noreply':
                From = readdress_configs.get_formatted_noreply()
            msg['From'] = From
            msg['To'] = message['email']
            s = smtplib.SMTP('localhost')
            s.send_message(msg)
            s.quit()
            logger.info ('len of {} is : {}'.format(mailerbackup, rclient.llen(mailerbackup)))
            rclient.lrem(mailerbackup, 0, item)
            logger.info ('len of {} is : {}'.format(mailerbackup, rclient.llen(mailerbackup)))
