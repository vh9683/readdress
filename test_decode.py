import json
import sys
import smtplib
import tempfile
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import email.utils

def decode_mail(ev):
  print ("TYPE EV : {}".format(type(ev)))
  if ev['msg']['spam_report']['score'] >= 5:
    print('Spam!!')
  else:
    print("*********************************************************\n")
    print('subject: ' + ev['msg']['subject'])
    print('text part: ' + ev['msg']['text'])
    print('html part: ' + ev['msg']['html'])
    print('from: ' + ev['msg']['from_email'])
    print('From: ' + ev['msg']['from_name'])
    for to,toname in ev['msg']['to']:
      print('to: ' + to)
      if toname:
        print('To: ' + toname)
    if 'attachments' in ev['msg']:
      for name,attachment in ev['msg']['attachments'].items():
        print('attachmet name ' + attachment['name'])
    if 'images' in ev['msg']:
      for name,image in ev['msg']['images'].items():
        print('image name ' + image['name'])
    print("*********************************************************\n")
    updatemail(ev)

def updatemail(ev):
    msg = MIMEMultipart('alternative')
    msg['To'] = email.utils.formataddr(('Recipient', "badari.hp@gmail.com"))
    msg['From'] = email.utils.formataddr((ev['msg']['from_name'], 'reply@inbound.edulead.in'))
    msg['Subject'] = ev['msg']['subject'] + "TESTING 2"
    text = ev['msg']['text']
    html = ev['msg']['html']
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    msg.attach(part1)
    msg.attach(part2)
    sendmail(ev, msg)
    print ("sent mail successfully")
    

def sendmail(ev, msg):
    print ("Tryingin to send mail\n")
    server = smtplib.SMTP('smtp.mandrillapp.com', 587)
    try:
        server.set_debuglevel(True)

        # identify ourselves, prompting server for supported features
        server.ehlo()

        # If we can encrypt this session, do it
        if server.has_extn('STARTTLS'):
            server.starttls()
            server.ehlo() # re-identify ourselves over TLS connection

        server.login('vidyartibng@gmail.com', 'c3JOgoZZ9BmKN4swnnBEpQ')
        server.sendmail(ev['msg']['from_email'], "badari.hp@gmail.com", msg.as_string())
    finally:
        server.quit()

if __name__ == "__main__":
    if (len(sys.argv) <= 1):
        raise ValueError("Script expects filename as arg")
    else:
        with open(sys.argv[1],'r') as f:
            records = json.load(f)
            for line in records:
                print("Data type line: {}".format(type(line)) )
                for keys in line:
                    print ("Type of {} :  {} ".format(keys, type( line[keys])) )
                    if isinstance(line[keys], dict) and keys == 'msg':
                        print ("Keys : {} , Values :  {} ".format(keys, "DICTONARY"))
                        decode_mail(line)
                    else:
                        print ("Keys : {} , Values :  {} ".format(keys, line[keys]))
                print ("\n\n==============================\n")

'''
with open('testmail.txt','r') as f:
  ev = json.load(f)
  if ev[0]['msg']['spam_report']['score'] >= 5:
    print('Spam!!')
  else:
    print('subject: ' + ev[0]['msg']['subject'])
    print('text part: ' + ev[0]['msg']['text'])
    print('html part: ' + ev[0]['msg']['html'])
    print('from: ' + ev[0]['msg']['from_email'])
    print('From: ' + ev[0]['msg']['from_name'])
    for to,toname in ev[0]['msg']['to']:
      print('to: ' + to)
      if toname:
        print('To: ' + toname)
    if 'attachments' in ev[0]['msg']:
      for name,attachment in ev[0]['msg']['attachments'].items():
        print('attachmet name ' + attachment['name'])
    if 'images' in ev[0]['msg']:
      for name,image in ev[0]['msg']['images'].items():
        print('image name ' + image['name'])
'''
