readdrsignup = """<h3>Just One More step to Get Started</h3>
<h4>Click on the below link and follow instructions to complete verification</h4>
<h4>https://readdress.io/verify/{{sessionid}}</h4>

<h5>note: The above link is valid only for few minutes and for one time use only. Please do not forward this to anyone.</h5>

<h5>You have received this in response to mail sent to signup@readdress.io, If you haven't sent the mail, please ignore this and may be it is a good idea to change password of your email service</h5>"""

readdressinvite = """<h3>Catch up with your friends on readdress.io</h3>
<h4>You have recieved this email since your friend {{ friend }} sent mail to you using readdress.io. Check out the features @ https://readdress.io</h4>
<h4>To signup right away, shoot a mail to signup@readdress.io with your phone number (in international format) as subject. You will get response mail with further instructions.</h4>

<h5>Warm Regards<br>Readdress.io</h5>"""

readdresspluscode = """<h3>Hi {{name}},</h3>
<h4>Plus+Code update {{outcome}}</h4>
<h5>Warm Regards,<br>Readdress.io</h5>"""

readdresswelcome = """<h3>Hi {{name}},</h3>
<h4>You have successfully completed the signup process and your Readdress.io Id {{id}} is ready to be shared.</h4>
<h4>Here's how you can send mail through Readdress, to someone who doesn't have Readdress.io Id:<br>Say you want to send mail to someone@example.com, then shoot mail to someone__example.com@readdress.io (it is two consectuive underscore), and we'll handle it from there. It's as simple as that!</h4>
<h4>If you didn't provide your home plus+code during signup, please do take a minute to provide same. Send your plus+code as subject to pluscode@readdress.io, head to http://plus.codes to get the code now!. You can update existing plus+code anytime in the same way.</h4>
<h4>Send us your feedback, feature request to feedback@readdress.io, we'll be glad to hear from you</h4>
<h5>Warm Regards<br>Readdress.io</h5>"""



mailtemplates = {'readdrsignup': { 'subject': 'Verify to Get Started', 'template': readdrsignup, 'from_email': 'Readdress.io <noreply@readdress.io>'},
                 'readdressinvite': { 'subject': 'Check out exciting features on readdress.io', 'template': readdressinvite, 'from_email': 'Readdress.io <noreply@readdress.io>'},
                 'readdresspluscode': { 'subject': 'Plus+Code Update', 'template': readdresspluscode, 'from_email': 'Readdress.io <noreply@readdress.io>'},
                 'readdresswelcome': { 'subject': 'Welcome to Readdress.io', 'template': readdresswelcome, 'from_email': 'Readdress.io <noreply@readdress.io>'},
}

