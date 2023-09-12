import os
import json
import typing as tp
import sqlite3
import pathlib

import requests
from solders.pubkey import Pubkey
from solana.rpc.api import Client as SolanaClient
from github import Github as GithubClient


SLACK_CHANNEL_WEBHOOK = os.environ.get("NEON_SLACK_CHANNEL")
SOLANA_CLUSTER_ENDPOINTS = {
    "devnet": "https://api.devnet.solana.com",
    "testnet": "https://api.testnet.solana.com",
    "mainnet-beta": "https://api.mainnet-beta.solana.com",
}

PROGRAM_ADDRESSES = {
    "metaplex": "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
}

GITHUB_ADDRESSES = {
    "solana": "solana-labs/solana",
    "spl": "solana-labs/solana-program-library",
    "metaplex": "metaplex-foundation/metaplex-program-library"
}


def init_db():
    if not pathlib.Path("versions.db").exists():
        db = sqlite3.connect("versions.db")
        cursor = db.cursor()
        with open("schema.sql", "r") as f:
            cursor.executescript(f.read())
        db.commit()
        db.close()


def get_solana_cluster_versions(solana_client: SolanaClient) -> dict:
    versions = {}
    for validator in solana_client.get_cluster_nodes().value:
        v = json.loads(validator.to_json())
        if v["version"] is None:
            continue
        if v["version"] not in versions:
            versions[v["version"]] = 0
        versions[v["version"]] += 1
    return versions


def get_github_versions(github_client: GithubClient, repo_name: str) -> list:
    repo = github_client.get_repo(repo_name)
    tags = repo.get_tags()[:10]
    return [tag.name for tag in tags]


def save_solana_cluster_versions(cluster_name: str, versions: dict):
    db = sqlite3.connect("versions.db")
    cursor = db.cursor()

    for version in versions:
        cursor.execute("""
        INSERT OR IGNORE INTO solana_clusters(cluster, version) VALUES (?, ?)
        """, (cluster_name, version))
    db.commit()
    db.close()


def save_github_versions(name: str, versions: list):
    db = sqlite3.connect("versions.db")

    cursor = db.cursor()
    for version in versions:
        cursor.execute("""INSERT OR IGNORE INTO github_versions(name,version) VALUES (?,?)""",
                       (name, version))
    db.commit()
    db.close()


def send_slack_notification(channel: str, message: str, blocks: tp.Optional[list] = None):
    body = {"text": message}
    if blocks:
        body["blocks"] = blocks
    requests.post(channel, json=body)


def notify_github_versions():
    db = sqlite3.connect("versions.db")
    cursor = db.cursor()

    cursor.execute("""SELECT name,version FROM github_versions WHERE notified = 0""")
    for line in cursor.fetchall():
        name, version = line
        try:
            send_slack_notification(
                SLACK_CHANNEL_WEBHOOK,
                f"New {name} version {version} was tagged in GitHub!",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"New <https://github.com/{GITHUB_ADDRESSES[name]}|{name}> was <https://github.com/{GITHUB_ADDRESSES[name]}/tree/{version}|tagged> in Github!"
                        }
                    }
                ]
            )
            cursor.execute("UPDATE github_versions SET notified=1 WHERE name=? AND version=?",
                           (name, version))
        except Exception as e:
            print(f"Can't send message to Slack: {e}")
    db.commit()
    db.close()


def notify_solana_cluster_versions():
    db = sqlite3.connect("versions.db")
    cursor = db.cursor()

    cursor.execute("""SELECT cluster,version FROM solana_clusters WHERE notified = 0""")
    for line in cursor.fetchall():
        cluster, version = line
        try:
            send_slack_notification(
                SLACK_CHANNEL_WEBHOOK,
                f"New Solana version {version} is available on {cluster} cluster!",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"New Solana version {version} is available on {cluster} cluster!"
                        }
                    }
                ]
            )
            cursor.execute("UPDATE solana_clusters SET notified=1 WHERE cluster=? AND version=?", (cluster, version))
        except Exception as e:
            print(f"Can't send message to Slack: {e}")
    db.commit()
    db.close()


def check_solana():
    for cluster_name in SOLANA_CLUSTER_ENDPOINTS:
        solana_client = SolanaClient(SOLANA_CLUSTER_ENDPOINTS[cluster_name])
        versions = get_solana_cluster_versions(solana_client)
        save_solana_cluster_versions(cluster_name, versions)
    notify_solana_cluster_versions()


def get_program_last_update(solana_client: SolanaClient, program_address: str):
    data = solana_client.get_account_info_json_parsed(Pubkey.from_string(program_address))
    program_account = data.value.data.parsed.get("info", {}).get("programData", None)
    if not program_account:
        print("Can't find program account for metaplex")
        return None
    program_data = solana_client.get_account_info_json_parsed(Pubkey.from_string(program_account))
    last_slot = program_data.value.data.parsed.get("info", {}).get("slot")
    return last_slot


def save_program_version(name: str, version: int, cluster: str):
    db = sqlite3.connect("versions.db")

    cursor = db.cursor()
    cursor.execute("""INSERT OR IGNORE INTO programs(name,cluster,last_slot) VALUES (?,?,?)""",
                   (name, cluster, version))
    db.commit()
    db.close()


def notify_programs_version():
    db = sqlite3.connect("versions.db")
    cursor = db.cursor()

    cursor.execute("""SELECT name,cluster,last_slot FROM programs WHERE notified = 0""")
    for line in cursor.fetchall():
        name, cluster, last_slot = line
        try:
            send_slack_notification(
                SLACK_CHANNEL_WEBHOOK,
                f"New {name} version {last_slot} was deployed in {cluster}!",
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"New <https://explorer.solana.com/address/{PROGRAM_ADDRESSES[name]}?cluster={cluster}|{name}> version was deployed in <https://explorer.solana.com/?cluster={cluster}|cluster> on {last_slot} slot!"
                        }
                    }
                ]
            )
            cursor.execute("UPDATE programs SET notified=1 WHERE name=? AND cluster=? AND last_slot=?", (name, cluster, last_slot))
        except Exception as e:
            print(f"Can't send message to Slack: {e}")
    db.commit()
    db.close()


def check_chain_programs():
    for cluster_name in SOLANA_CLUSTER_ENDPOINTS:
        solana_client = SolanaClient(SOLANA_CLUSTER_ENDPOINTS[cluster_name])
        for program_name in PROGRAM_ADDRESSES:
            if isinstance(PROGRAM_ADDRESSES[program_name], dict):
                program_address = PROGRAM_ADDRESSES[program_name].get(cluster_name)
            else:
                program_address = PROGRAM_ADDRESSES[program_name]

            version = get_program_last_update(solana_client, program_address)
            if version:
                save_program_version(program_name, version, cluster_name)


def check_github_versions():
    github_client = GithubClient()

    for program_name in GITHUB_ADDRESSES:
        versions = get_github_versions(github_client, GITHUB_ADDRESSES[program_name])
        save_github_versions(program_name, versions)


if __name__ == "__main__":
    init_db()
    check_solana()
    check_chain_programs()
    check_github_versions()
    notify_github_versions()
    notify_programs_version()
