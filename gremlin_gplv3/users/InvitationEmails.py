from django.core.mail import EmailMultiAlternatives
from sendgrid import *
from sendgrid.helpers.mail import Mail

def SendInviteEmail(username, name, password, email):

    try:
        sg = sendgrid.SendGridAPIClient(api_key="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")
        from_email = Email("test@example.com")
        to_email = To(email)
        subject = 'Welcome to GREMLIN - The Low-Code Microservices Framework'
        content = Content("text/plain", f"Dear {name},\nWelcome to GREMLIN. Your login details are as follows.\n\n\tUsername: {username}\n\tPassword:"
             f" {password}\n\nYou can change your password by going to the Settings tab and clicking 'Change Password'.")
        mail = Mail(from_email, to_email, subject, content)
        response = sg.client.mail.send.post(request_body=mail.get())
        print(response.status_code)
        print(response.body)
        print(response.headers)

    except Exception as e:
        print(e.message)
