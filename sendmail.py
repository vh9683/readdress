#! /usr/bin/python3.4


import sys
from redis import StrictRedis
from bson import Binary
import pymongo
import pickle

def sendmail(ev, msg, to):
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

      gen_log.info('RCPT : {}'.format(to))

      composed = msg.as_string()
      gen_log.info('Actual Msg : {}'.format(composed))
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
        sendmail(ev, msgtuple[1], msgtuple[0])
      else:
        pass
    else:
        pass
    #No need to remove from redis .. it will be removed after expiry
    print ('len of sendmailbackup is : {}'.format(r.llen('sendmailbackup')))
    r.lrem('sendmailbackup', 0, item)
    print ('len of sendmailbackup is : {}'.format(r.llen('sendmailbackup')))
