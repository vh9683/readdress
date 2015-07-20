#!/usr/bin/python3.4
import re
import json
import sys
import smtplib
import tempfile
import mimetypes
import email.utils
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import uuid

from map_email import emap


indent = 1
'''
def print_dict(dic, name):
    print ("DICTONARY : {} -->".format(name))
    space ='|'
    print ('++++++++++++++++++++++++++++++++++++++++++++++++++++\n')
    global indent

    for i in range(indent):
        space += '- '

    for i in dic:
        if not isinstance(dic[i], dict):
            print ('{} keys[{}]                :  {}\n'.format(space, i, dic[i]))
        else:
            print_dict(dic[i], i)
    print ('++++++++++++++++++++++++++++++++++++++++++++++++++++\n')
    indent += 1
'''

mapper = dict()
mapper['9686111887@inbound.edulead.in'] = 'badariprasad.h@gmail.com'
mapper["9845837392@inbound.edulead.in"] = 'smitah3@gmail.com'
mapper["badari.hp@inbound.edulead.in"]  = 'badari.ph@gmail.com'
mapper['harish@inbound.edulead.in']     = 'harish.v.murthy@gmail.com'

reversemap = dict()
reversemap['badariprasad.h@gmail.com']  = '9686111887@inbound.edulead.in'
reversemap['smitah3@gmail.com']         = "9845837392@inbound.edulead.in"
reversemap['badari.ph@gmail.com']       = "badari.hp@inbound.edulead.in"
reversemap['harish.v.murthy@gmail.com'] = 'harish@inbound.edulead.in'


def lookup(email):
  mappedmail =  mapper.get(email) 
  return mappedmail

def getpsuedomail(email):
  mappedmail =  reversemap.get(email) 
  return mappedmail

def populate_addresses(ev, msg, keys):
    bccmightbepresent = True
    
    rcptslist = list()

    msg['From'] = email.utils.formataddr((ev['msg']['from_name'], ev['msg']['from_email']))

    toaddresses =""
    if 'to' in keys:
      for to,toname in ev['msg']['to']:
        #print('to: ' + to)
        mto = ""
        if 'inbound' in to :
          mto = lookup(to)
        else:
          mto = getpsuedomail(to)

        if mto is None:
           mto = to

        if toname:
            toaddresses += email.utils.formataddr((toname,mto)) + ','
        else:
            toaddresses += mto + ','

        rcptslist.append(mto)

    msg['To'] = toaddresses

    ccaddresses = ""
    if 'cc' in keys:
      for cc,ccname in ev['msg']['cc']:
        mcc = ""
        if 'inbound' in cc :
          mcc = lookup(cc)
        else:
          mcc = getpsuedomail(cc)

        if mcc is None:
           mcc = cc

        if ccname:
            ccaddresses = email.utils.formataddr((ccname,mcc)) + ','
        else:
            ccaddresses += mcc + ','
        rcptslist.append(mcc)

    msg['Cc'] = ccaddresses
    msg['X-MC-PreserveRecipients'] = 'true'

    ''' 
    bccmail = list()
    if bccmightbepresent:
        msg['X-MC-PreserveRecipients'] = 'false'
        recvdlist = (ev['msg']['headers']['Received'])
        for i in recvdlist:
            match = re.search('([\w.-]+)@([\w.-]+)', i)
            if match is not None:
                bccemail = match.group()
                if 'edulead' in bccemail and 'from' in i:
                    bccmail.append(bccemail)
        setaddr = set(bccmail)
        bccmail = list(setaddr)
        rcptslist.append(bccmail)
        msg['Bcc'] = ','.join(bccmail)
    '''

    return rcptslist

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
    keys = [ k for k in ev['msg'] if k in ev['msg'].keys() ]
    values = [ k for k in ev['msg'] if k in ev['msg'].values() ]
    print ("Keys {}".format(keys))
    print ("Type of keys : {}".format(type(ev['msg'])))
    print("*********************************************************\n")
    
    '''
    print ("------------------------------------------\n")
    for k in ev:
        print ('1 keys[{}]                :  {}\n'.format(k[0], k[1]))
        if isinstance(ev[k], dict):
            print ("------\n")
            dic = ev[k]
            print_dict(dic, k)
            print ("------\n")
            
    print ("------------------------------------------\n")
    '''
    
    msg = MIMEMultipart('alternative')
    rcptslist = populate_addresses(ev, msg, keys)
    updatemail(ev, msg, keys)

    sendmail(ev, msg, rcptslist)
    print ("sent mail successfully")

def updateAttachments(ev, msg, keys):
    if 'attachments' in keys:
      for name,attachment in ev['msg']['attachments'].items():
        file_name = attachment['name']
        aType = attachment['type']
        if aType is None:
            aType = 'application/octet-stream'
        isBase64 = attachment['base64']
        maintype, subtype = aType.split('/', 1)
        if 'text' == maintype:
            part = MIMEText(attachment['content'], subtype)
        elif 'audio' == maintype:
            part = MIMEAudio(attachment['content'], subtype)
        else:
            part = MIMEBase(maintype, subtype)
            part.set_payload(attachment['content'])

        # Encode the payload using Base64
        if isBase64:
            encoders.encode_base64(part)
        # Set the filename parameter
        if file_name is not None:
            part.add_header('Content-Disposition', 'attachment', filename=file_name)
        else:
            raise ValueError("File name missing")
        msg.attach(part)

    if 'images' in keys:
      for image in ev['msg']['images'].items():
        file_name = images['name']
        aType = images['type']
        isBase64 = images['base64']
        img = MIMEImage(image['content'] ,_subtype=subtype)
        if isBase64:
            encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment', filename=file_name)
        msg.attach(img)

def updatemail(ev, msg, keys):
    msg['Subject'] = ev['msg']['subject'] + "TESTING 2"
    text = ev['msg']['text']
    html = ev['msg']['html']
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(html, 'html')
    msg.attach(part1)
    msg.attach(part2)

    updateAttachments(ev, msg, keys)

    

def sendmail(ev, msg, to):
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

        print ('RCPT : {}'.format(to))
        REPLY_TO_ADDRESS = (uuid.uuid1().urn[9:]) + '@inbound.edulead.in'
        REPLY_TO_ADDRESS.replace('-','')
        print('REPLY_TO_ADDRESS : {}'.format(REPLY_TO_ADDRESS))
        msg.add_header('reply-to', REPLY_TO_ADDRESS)
        composed = msg.as_string()
        print ("ACTUAL MSG \n {} \n".format(composed))
        server.sendmail(ev['msg']['from_email'], to, composed)
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
