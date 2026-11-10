import io
import os
import unittest
from email.message import EmailMessage
from unittest.mock import patch

import pandas as pd

import collector


def _xlsx_attachment(filename, timestamp, value_kwh):
    frame = pd.DataFrame([
        ["header"] * 6,
        ["header"] * 6,
        [timestamp, "", "", "", "", value_kwh],
    ])
    output = io.BytesIO()
    frame.to_excel(output, index=False, header=False)

    message = EmailMessage()
    message['From'] = 'reports@example.test'
    message['Subject'] = filename
    message['Message-ID'] = f'<{filename}>'
    message.set_content('report')
    message.add_attachment(
        output.getvalue(),
        maintype='application',
        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=filename,
    )
    return message.as_bytes()


class FakeMail:
    messages = {
        'FusionSolar': {
            b'1': _xlsx_attachment(
                'report07-11-2026.xlsx', '2026-11-07 10:00:00', 5000
            ),
        },
        'INBOX': {
            b'2': _xlsx_attachment(
                'report08-11-2026.xlsx', '2026-11-08 10:00:00', 6000
            ),
        },
        '[Gmail]/All Mail': {
            b'3': _xlsx_attachment(
                'report08-11-2026.xlsx', '2026-11-08 10:00:00', 6000
            ),
        },
    }

    def __init__(self, *_args, **_kwargs):
        self.folder = None
        self.logged_out = False

    def login(self, _user, _password):
        return 'OK', []

    def select(self, folder, readonly=False):
        self.folder = folder.strip('"')
        return ('OK', [str(len(self.messages[self.folder])).encode()])

    def search(self, *_args):
        return 'OK', [b' '.join(self.messages[self.folder].keys())]

    def fetch(self, message_id, _query):
        return 'OK', [(b'RFC822', self.messages[self.folder][message_id])]

    def logout(self):
        self.logged_out = True
        return 'BYE', []


class EmailFactCollectionTests(unittest.TestCase):
    def test_reads_all_folders_and_deduplicates_same_message(self):
        env = {
            'EMAIL_USER': 'user@example.test',
            'EMAIL_PASS': 'password',
            'EMAIL_FOLDERS': 'FusionSolar,INBOX,"[Gmail]/All Mail"',
        }
        with patch.dict(os.environ, env, clear=False), patch.object(
            collector.imaplib, 'IMAP4_SSL', FakeMail
        ):
            facts = collector.read_facts_from_email(days=30)

        self.assertEqual(len(facts), 2)
        self.assertEqual(
            sorted(round(row['Fact_MW'], 3) for row in facts),
            [5.0, 6.0],
        )


if __name__ == '__main__':
    unittest.main()
