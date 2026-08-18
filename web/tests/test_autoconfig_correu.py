"""The mail autoconfig we publish must match where the mail actually is.

It is a **copy** of what Purelymail already serves at
`autoconfig.purelymail.com`, and copies drift: this very file used to
tell clients to send through a Brevo relay with a shared API key, months
after that stopped being true, so a new mailbox could receive and not
send.

We publish it anyway because Spark Desktop reads the domain's own
autoconfig and, without it, keeps whatever it had — and then refuses to
let the servers be edited, so the only way out is deleting the account
and losing its local configuration.

These checks are cheap and they pin the two things that made the last
drift dangerous: that the hosts are Purelymail's, and that the password
is the mailbox's own rather than a shared credential.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

FITXER = (
    Path(__file__).resolve().parent.parent.parent
    / "deploy"
    / "autoconfig-topquaranta.xml"
)
NS = ""


def _arbre():
    return ElementTree.fromstring(FITXER.read_text())


def test_the_file_is_valid_xml():
    assert _arbre().tag == "clientConfig"


def test_both_servers_point_at_purelymail():
    """The host the mail is on. A stale hostname here is a client that
    silently cannot connect."""
    arbre = _arbre()
    incoming = arbre.find(".//incomingServer/hostname").text
    outgoing = arbre.find(".//outgoingServer/hostname").text
    assert incoming == "imap.purelymail.com"
    assert outgoing == "smtp.purelymail.com"


def test_the_ports_and_encryption_match_purelymail():
    arbre = _arbre()
    assert arbre.find(".//incomingServer/port").text == "993"
    assert arbre.find(".//outgoingServer/port").text == "465"
    for node in arbre.findall(".//socketType"):
        assert node.text == "SSL"


def test_the_credential_is_the_mailbox_not_a_shared_key():
    """The Brevo era: the username was a shared SMTP account and the
    password an API key, published in this very file. Both servers must
    ask for the person's own address."""
    for node in _arbre().findall(".//username"):
        assert node.text == "%EMAILADDRESS%"


def test_no_third_party_relay_is_advertised():
    """Only Purelymail may appear as a server. Checked on the parsed
    values, not the file text: the comment above explains the Brevo
    episode on purpose, and history is not configuration."""
    hosts = [n.text for n in _arbre().findall(".//hostname")]
    assert hosts, "cap servidor declarat"
    for host in hosts:
        assert host.endswith(".purelymail.com"), host
