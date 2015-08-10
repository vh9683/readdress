#! /usr/bin/python3.4

import sys
import re
import base64
import pymongo
import pickle
import logging
import logging.handlers
import copy
import uuid
import time
import email.utils 
from email.utils import parseaddr
from redis import StrictRedis

FILESIZE=1024*1024*1024 #1MB
instance = "0"
try:
  conn=pymongo.MongoClient()
  print ("Connected successfully!!!")
except pymongo.errors.ConnectionFailure as e:
  print ("Could not connect to MongoDB: %s" % e )

db = conn.inbounddb
rclient = StrictRedis()
logger = logging.getLogger('mailHandler')
formatter = logging.Formatter('MAILHANDLER-['+instance+']:%(asctime)s %(levelname)s - %(message)s')
hdlr = logging.handlers.RotatingFileHandler('/var/tmp/mailhandler.log', 
                                            maxBytes=FILESIZE, backupCount=10)
hdlr.setFormatter(formatter)
logger.addHandler(hdlr) 
logger.setLevel(logging.DEBUG)

OUR_DOMAIN = 'inbound.edulead.in'

REDIS_MAIL_DUMP_EXPIRY_TIME = 60

def getdomain(a):
  return a.split('@')[-1]
  
def getuserid(a):
  return a.split('@')[0]

def isourdomain( a):
  return getdomain(a) == OUR_DOMAIN

def isknowndomain(a):
  if isourdomain(a):
    return True
  known = db.domains.find_one({'domain': getdomain(a)})
  if not known:
    return False
  return True

def getuser(a):
  if isourdomain(a):
    user = db.users.find_one({'mapped': a})
  else:
    user = db.users.find_one({'actual': a})
  return user

def getmapped(a):
  user = getuser(a)
  if not user:
    return None
  return user['mapped']

def newmapaddr(a):
  mapped = getmapped(a)
  if not mapped:
    mapped = uuid.uuid4().hex+'@'+OUR_DOMAIN
    db.users.insert({'mapped': mapped, 'actual': a})
    logger.info('insterted new ext user ' + a + ' -> ' + mapped)
  return mapped

def populate_from_addresses(msg):
  fromstring = msg['From']
  fromname, fromemail = parseaddr(fromstring)
  logger.info("Actual From address {} {}".format(fromname, fromemail))
  mapped = newmapaddr(fromemail)
  if not mapped:
    return False
  del msg['From']
  if fromname:
    msg['From'] = email.utils.formataddr((fromname, mapped))
  else:
    msg['From'] = mapped
  logger.info('From: ' + str(msg['From']))
  return True, fromemail

def getToAddresses(msg):
  tostring = msg.get('To')
  tolst = tostring.split(',')
  tolst = [to.strip() for to in tolst if not 'undisclosed-recipient' in to]
  torecipients = []
  for toaddr in tolst:
    toname,to  = parseaddr(toaddr)
    to = [to, toname]
    torecipients.append(to)
  return torecipients

def getCcAddresses(msg):
  ccrecipients = []
  ccstring = msg.get('Cc')
  if ccstring is None:
    return ccrecipients
  cclst = ccstring.split(',')
  cclst = [cc.strip() for cc in cclst if not 'undisclosed-recipient' in cc]
  for ccaddr in cclst:
    ccname,cc  = parseaddr(ccaddr)
    cc = [cc, ccname]
    ccrecipients.append(cc)
  return ccrecipients
 

def checkForBccmail (msg):
  receivedhrds = msg.get_all('Received')
  bccinmail = False
  bccemail = []
  for hdr in receivedhrds:
    logger.info("Received header \n {}".format(hdr))
    match = re.search('([\w.-]+)@([\w.-]+)', hdr)
    if match is not None:
      mailaddr = match.group()
      bccinmail = True
      bccemail.append(mailaddr)
    
  if bccinmail:
    logger.info('Mail contains BCC email addresses in Received Header... Dropping Mail')
    logger.info("Bcc Emails Addresses are : {}".format( ', '.join(bccemail)))

  return bccinmail

def valid_uuid4(a):
  userid = getuserid(a)
  try:
    val = uuid.UUID(userid, version=4)
  except ValueError:
    # If it's a value error, then the string 
    # is not a valid hex code for a UUID.
    return False

  # If the uuid_string is a valid hex code, 
  # but an invalid uuid4,
  # the UUID.__init__ will convert it to a 
  # valid uuid4. This is bad for validation purposes.
  return val.hex == userid

def isregistereduser(a):
  """ check whether the user address is a registered one or generated one """
  return not valid_uuid4(a)

def valid_email_addresses (msg,allrecipients,from_email):
  for id,name in allrecipients:
    success = isregistereduser(id)
    if success:
      return True
  success =  getuser(from_email)
  if success:
    return True
  return False
 

def validthread(msg,allrecipients,from_email):
  """ 
      Every new thread must come from known domain and
      and very mail must have at least one regiestered user
      who can be the sender or recepient
  """
  ''' A useful thread identification algorithm is explained in 
      http://www.jwz.org/doc/threading.html ...
      
      NOTES:
            References header: will contains list of all message id's for tentire converstion.
            Oldest MsgId being the first. Header contain a list of Message-IDs listing the parent, grandparent, great-grandparent, 
            and so on, of this message, oldest first. 
            That is, the direct parent of this message will be the last element of the References header.
            NewsGroups are allowed to truncate the refrences header.

            In-Reply-To Header will (most of times) contain the msgid of recent message for which reply is being sent to.
            
            New Mail will not contein In-ReplyTo and References header. It will contain MsgId header only.


    Design:
        1) For each new mail received we need to store msgId as key and value "" (mails which does not contain In-Reply-To header)
        2) For each reply mail, we need to get the refrences header and in-reply-to id and search in collections for existing entries.
           Get In-Reply-To header mostly contains the msgId of previous mail, search is int the collection and get the actual msgId
           and check if it is the head of references header. If these check passed the thread is valid.
           Now add the nre msgId of reply mail into the values section for the original msgId stored in the mongodb
           Or 
           if in-reply-to value is part of any documents of existing treat this as valid thread and add the msgid of reply mail in to 
            the document.
        3) Handling duplicates, if the msgId of the new reply mail is part of any existing documents of db then treat this mail as 
        duplicate. We need not handle this mail.

        For above logic we may think of adding subject as well. for all reply mails we can match the existing subject line excluding "re:" 
        charactes of the reply mail subject line.

    Notes:
     1) For new mails the existing gmail , other mail servers does not produce multiple inbound triggers for mail id's in cc header.
     2) But for reply path the gmail and other servers does produce multiple inbound triggers (possibly with same msgId) for each
     mail id in cc header.

  '''

  msgId = msg.get("Message-ID") 
  if msgId is None:
    return False

  msgId = msgId.strip()

  inreplyto = msg.get("In-Reply-To")
  ''' References are seperated by '\n\t' oldest thread id being the first id in references '''
  references = msg.get('References')
  if inreplyto is not None:
    inreplyto = inreplyto.strip()
  if references is not None:
    references = references.strip()

  if inreplyto is None and references is None:
    mailthread = db.threadMapper.find_one( { 'threadId' : msgId } )
    if mailthread is None:
      ''' no mail with msgId found in DB .. insert new entry in the db''' 
      db.threadMapper.insert( { 'threadId' : msgId } )
      logger.info("Inserting new doc")
      return True
    else:
      logger.info("Possible Duplicate mail")
      return False
  elif inreplyto is not None and references is not None:
    mailthread = db.threadMapper.find_one( { 'threadId' : msgId } )
    if mailthread is not None:
        logger.info("Is this case possible ??? ")
        raise ValueError("msgId present in db, inreplyto / references also received in mail")
  else:
    op = { 'references': {'$in' : [inreplyto]}}
    mailthread = db.threadMapper.find( op )

    logger.info ("MSGID {} . inreplyto : {} . references {} ".format(msgId, inreplyto, references))
    logger.info ("mail therad : {} \n".format( mailthread))
    if mailthread is not None:
        entries = list(mailthread[:])
        logger.info(entries)
        logger.info(len(entries))
        if 'references' not in entries:
          ''' if its reply path references might not be present in db .. 
          could be very first reply to the mail thread'''
          op = { '$push' : { 'references' : msgId }}
          result = db.threadMapper.update( { 'threadId' : inreplyto }, op , False, False )
          logger.info("Result : {}".format(result))
          return True
        elif 'references' in entries:
          '''  reply path mail need to check if its duplicate '''
          logger.info(entries['references'])
          if msgId in entries['references']:
            logger.info("mail already handled.. duplicate mail")
            return False
          else:
            op = { '$push' : { 'references' : msgId }}
            db.threadMapper.update( { 'threadId' : mailthread['threadId'] }, op , False, False )
            return True
    if mailthread is None:
      #???    
      mailthread = db.threadMapper.find_one( { 'threadId' : inreplyto } )
      if mailthread is not None:
        entries = list(mailthread[:])
        if msgId in entries['references']:
            return False #Dupilcate Mail
        else:
          op = { '$push' : { 'references' : msgId }}
          result = db.threadMapper.update( { 'threadId' : inreplyto }, op , False, False )
          return True

 
def isUserEmailTaggedForLI(a):
  """ Check if the user address is tagged for LI """
  user = getuser(a)
  if user and 'tagged' in user: 
    return user['tagged']
  return None

def getactual(a):
  user = getuser(a)
  if not user:
    return None
  return user['actual']


def mapaddrlist(li):
  rli = []
  logger.info('mapaddrlist li ' + str(li))
  for x in li:
    mapped = getmapped(x[0])
    if not mapped:
      continue
    if x[1]:
      rli.append(email.utils.formataddr((x[1],mapped)))
    else:
      rli.append(mapped)
  logger.info('mapaddrlist rli ' + str(rli))
  return rli

def sendmail( evKey, msg, to):
  key = uuid.uuid4().hex + ',' + evKey
  rclient.set(key, pickle.dumps((to, msg)))
  ''' mark key to exipre after 15 secs'''
  key = key.encode()
  rclient.expire(key, 25)
  rclient.lpush('sendmail', key)
  logger.info("sendmail key {}".format(key))
  return

if __name__ == '__main__':
  instance = sys.argv[-1]

  if not instance:
    instance = "1"

  ''' 
    SPAM check is not done here ... it should have been handled in earlier stage of pipeline
  '''
  while True:
    item = rclient.brpoplpush('mailhandler', 'mailhandlerBackUp')
    ev = pickle.loads(item)
    emaildump = (ev['msg']['raw_msg'])
    origmsg = email.message_from_string(emaildump)
    ''' Just to keep back up of orig mail'''
    msg = copy.deepcopy(origmsg)
    del msg['DKIM-Signature']
    
    '''
    if checkForBccmail(msg):
      #Dropping mail
      continue
   '''

    ''' handle ev msg here 
        1) parse raw msg
        2) check for validity
        3) check if bcc mail and drop the mail / do some thing
        4) move the completed section to other parts such as li / sendmail or some thing else
    '''
    torecipients = getToAddresses(msg)
    ccrecipients = getCcAddresses(msg)
    allrecipients = torecipients + ccrecipients
    del msg['To']
    del msg['Cc']

    success,fromemail= populate_from_addresses(msg)
    if not success:
      logger.info('Error adding from address')
      raise ValueError

    taggedList = []
    for mailid,name in allrecipients:
      if isUserEmailTaggedForLI(mailid):
        taggedList.append(mailid)

    if isUserEmailTaggedForLI(fromemail):
        taggedList.append(fromemail)

    ''' stage 2 check for Law Interception for all mails '''
    if len(taggedList):
      item = []
      item.append(','.join(taggedList))
      item.append(ev)
      rclient.lpush('liarchive', pickle.dumps(item))
       
    success = valid_email_addresses(msg, allrecipients, fromemail)
    if not success:
      logger.info("Not a valid mail thread!! email address check failed, dropping...")
      raise ValueError("Invalid email addresses")

    success = validthread(msg, allrecipients, fromemail)
    if not success:
      logger.info("Not a valid mail thread!!, dropping...")
      raise ValueError("Invalid thread credentials")
    msg['X-MC-PreserveRecipients'] = 'true'

    ''' msg will have Message-ID In-ReplyTo and References '''
    #if 'Message-Id' in ev['msg']['headers']:
    #  msg.add_header("Message-Id", ev['msg']['headers']['Message-Id'])
    #if 'In-Reply-To' in ev['msg']['headers']:
    #  msg.add_header("In-Reply-To", ev['msg']['headers']['In-Reply-To'])
    #if 'References' in ev['msg']['headers']:
    #  msg.add_header("References", ev['msg']['headers']['References'])
               
    evKey =  uuid.uuid4().hex
    rclient.set(evKey, pickle.dumps(ev))
    ''' mark key to exipre after REDIS_MAIL_DUMP_EXPIRY_TIME secs '''
    ''' Assuming all mail clients to sendmail witn in REDIS_MAIL_DUMP_EXPIRY_TIME '''
    rclient.expire(evKey, REDIS_MAIL_DUMP_EXPIRY_TIME)
    mail_count = 0
    for mailid in allrecipients:
      if not isourdomain(mailid[0]):
        continue
      rto = mapaddrlist(allrecipients)
      actual = getactual(mailid[0])
      if not actual:
        continue
      if mailid[1]:
        recepient = email.utils.formataddr((mailid[1],actual))
        tremove = email.utils.formataddr((mailid[1],mailid[0]))
      else:
        recepient = actual
        tremove = mailid[0]
      if tremove in rto:
        rto.remove(tremove)
      if msg['From'] in rto:
        rto.remove(msg['From'])
      if 'To' in msg:
        del msg['To']
      if 'Cc' in msg:
        del msg['Cc']
      logger.info('To: ' + str(rto))
      msg['To'] = ','.join(rto)
      logger.info("Pushing msg to sendmail list {}\n".format(recepient))
      sendmail(evKey, msg, recepient)
 
    logger.info ('len of emailhandler mailhandlerBackUp is : {}'.format(rclient.llen('mailhandlerBackUp')))
    rclient.lrem('mailhandlerBackUp', 0, item)
    logger.info ('len of emailhandler mailhandlerBackUp is : {}'.format(rclient.llen('mailhandlerBackUp')))

    del origmsg
    del msg
    del ev
