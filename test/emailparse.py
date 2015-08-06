#!/usr/bin/python3.4
import re
import json
import sys
import smtplib
import tempfile
import mimetypes
import email
import email.utils
from email import encoders
from email.message import Message
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.headerregistry import Address
import uuid
import base64
import copy
from email.utils import parseaddr


def parseremail(emaildump):
    msg = email.message_from_string(emaildump)
    print ('=================\n')
    for part in msg.walk():
        print ("-----------------------> {}".format(part.get_content_type()))
        print ( " {} . {} ".format(len (part.get_payload()), type(part.get_payload())) )
        ep = (part.get_payload())
        if isinstance(ep, dict):
            for i in ep:
                print('dict *******************************>')
                print (ep[i])
                print('<*******************************>')
        elif isinstance(ep, list):
            for i in ep:
                print('list *******************************>')
                print ("Type {} , {} : {} ".format(type(i), i.is_multipart(), i))
                print('<*******************************>')
        elif isinstance(ep, str):
            print (ep)
        print ("<-----------------------> ")
    print ('=================\n')

    print ("TYpe : {}".format(type(msg)))
    for part in msg:
        print (part)

    print ("TYPE {} : ID {} , LEN : {}".format(type(msg), id(msg), len(msg) ))
    msg1 = copy.deepcopy(msg)
    print ("TYPE {} : ID {} , LEN : {} ".format(type(msg1), id(msg1), len(msg1)))

    for i in msg.items():
        print (i)
    
    toaddstr = msg1['To']
    del msg1['To']
    if toaddstr:
        tolst = toaddstr.split(',')
        for i in tolst:
            n, e = parseaddr(i)
            print ("Parsed email : {}  : {} ".format (n, e))

    

if __name__ == "__main__":
    if (len(sys.argv) <= 1):
        raise ValueError("Script expects filename as arg")
    else:
        with open(sys.argv[1],'r') as f:
            records = json.load(f)
            #print (records[0]['msg']['raw_msg'])
            emaildump = (records[0]['msg']['raw_msg'])
            print ('emaildump type {}'.format(type(emaildump)))
            parseremail(emaildump)
            
             
 
