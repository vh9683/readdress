#! /usr/bin/python3.4


import sys
from redis import StrictRedis
from bson import Binary
import pymongo
import pickle
import logging
import logging.handlers

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

def sendmail(ev, msg, to, logger):
    ''' function to be optimised ''' 
    server = smtplib.SMTP('smtp.mandrillapp.com', 587)
    try:
      #server.set_debuglevel(True)

      # identify ourselves, prompting server for supported features
      server.ehlo()

      # If we can encrypt this session, do it
      if server.has_extn('STARTTLS'):
        server.starttls()
        server.ehlo() # re-identify ourselves over TLS connection
        server.login('vidyartibng@gmail.com', 'c3JOgoZZ9BmKN4swnnBEpQ')

      logger.info('RCPT : {}'.format(to))

      composed = msg.as_string()
      logger.debug('Actual Msg : {}'.format(composed))
      server.sendmail(ev['msg']['from_email'], to, composed)
    finally:
      server.quit()

if __name__ == '__main__':
  instance = sys.argv[-1]

  if not instance:
    instance = "1"

  try:
    conn=pymongo.MongoClient()
    print ("Connected successfully!!!")
  except pymongo.errors.ConnectionFailure as e:
    print ("Could not connect to MongoDB: %s" % e )

  db = conn.inbounddb.liMailBackUp
  r = StrictRedis()

  logger = logging.getLogger('sendmail')
  formatter = logging.Formatter('SENDMAIL:%(asctime)s %(levelname)s %(message)s')
  hdlr = logging.handlers.RotatingFileHandler('/var/tmp/sendmail.log', 
                                            maxBytes=FILESIZE, backupCount=10)
  hdlr.setFormatter(formatter)
  logger.addHandler(hdlr) 
  logger.setLevel(logging.DEBUG)

  while True:
    item = r.brpoplpush('sendmail', 'sendmailbackup')
    #Get the smtp msg from redis
    if r.exists(item):
      msgtuplepickle = r.get(item)
      msgtuple = pickle.loads(msgtuplepickle)
      #Get the inbound json obj from redis
      keys = item.split(',')
      evKey = keys[1]
      if r.exists(evKey):
        evpickle = r.get(evKey)
        ev = pickle.loads(evpickle)
        sendmail(ev, msgtuple[1], msgtuple[0]), logger)
      else:
        pass
    else:
        pass
    #No need to remove from redis .. it will be removed after expiry
    logger.info('len of sendmailbackup is : {}'.format(r.llen('sendmailbackup')))
    r.lrem('sendmailbackup', 0, item)
    logger.info('len of sendmailbackup is : {}'.format(r.llen('sendmailbackup')))
