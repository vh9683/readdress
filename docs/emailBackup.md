
As of now inbound emails are dummped as json document in below format
   <from_email> : <json_document>
emails are backedup in db : inbound.backup
Example:
yield inbounddb.mailBackup.insert( {'from':ev['msg']['from_email'], 'inboundJson':ev} )


