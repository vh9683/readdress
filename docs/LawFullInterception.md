Purpose of LI is to track any tagged user for suspecious activity and send all the transactions made by
such tagged users to Law agencies.

As of now the ['X-MC-BccAddress'] will be used to send copy of all the tagged transaction to email id registered by
Law agencies

The DB design is as follows:

1) Have a field in users collection for tracking tagged emails 
    : as of now users has field 'actual' and 'mapped', a new field 'tagged' is to be added
2) In tagged field , email id if law agencies can be maintained.
    It could be possible that different agencies could track diff emails, for this reason for each tagged user email a law enforecment agency email id will be needed.

