# This is main codebase #
## Be sure to save your work and ##

## Design decisions ##

Assumptions: From address will not our own

Scenario 1:
A and B are registered users with 1 and 2 being there numbers
C is the sender
D is another receipent who is not a registered user

first post to us will have
from: C
To: 1,2,D

  D would have already received the mail since its routed directly
  We loop through the receipents and for each user of our domain found:
  get the mapped mail id: 1 -> A, 2 -> B
  transform the from address to our domain: C -> 3 (this is a base64 encoded id, so can be distinguished from other registered addresses)
  transform other non-registered recepients to our domain: D -> 4 (this it make sure the replies do not reach directly
                                                                   revealing the true identities of registered users)
  the actual recepient will be the mapped mail id
  the To & cc header will be populated skipping the receipent and with addresses from our domain
  in all outbound mail, the from, to & cc header will always have addresses from our domain only

  All intial posts will not have "In-Reply-To" header, in such cases we need to create a new transaction and save the "Message-Id" header
  The transacion id needs to be added to message either in "Message-Id" header or in "X-MC-Metadata" header or "References" header

  Recepient: A
  From: 3
  To: 2,4

  Recepient: B
  From: 3
  To: 1,4

Now if A or B "reply" to mail, we receive a post like
  To: 3
  From: A

  If we apply the logic as before
  Since this is reply, the message will have "In-Reply-To" header, in such cases we need to retrive the transaction id from message
  and include original message id in "In-Reply-To" header of outbound mails

  Recepient: C
  From: 1
  To: 3
  
Now if A does "reply all", we receive a post like
  To: 2, 3, 4
  From: A

  If we apply the logic as before

  Recepient: C
  From: 1
  To: 2,4

  Recepient: B
  From: 1
  To: 3,4

  Recepient: D
  From: 1
  To: 2,3

  If D does "reply all" to the original mail he got (directly from C)
  When we transform from address, we detect that D is not a registered user

  From: D
  To: C,1,2

  If we apply same logic for sending

  Recepient: A
  From: 4
  To: 2,3

  Recepient: B
  From: 4
  To: 1,3

Scenario 2: Registered user starts a mail chain
Say one of the registered user starts a mail chain, then he would only keep registered users in the To & Cc header
otherwise his identity cannot be hidden

  From: A
  To: 2,5

  If we apply the same logic as before

  Recepient: B
  To: 5
  From: 1

  Recepient: E
  To: 2
  From: 1

  The "reply all" cases would be

  From B:
  To: 1,5

  So applying transform logic

  Recepient: A
  From: 2
  To: 5

  Recepient: E
  From: 2
  To: 1
