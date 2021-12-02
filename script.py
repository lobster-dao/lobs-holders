#!/usr/bin/env python3.8
from datetime import datetime, timezone
from pathlib import Path
import csv
import os

import brownie
from brownie import Contract, chain

github_repo_raw_path = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/raw/'

def main():
    brownie.network.connect('mainnet')

    # lobsterdao, or plop your contract addr here
    nft_contract = Contract.from_explorer('0x026224a2940bfe258d0dbe947919b62fe321f042')
    block_id = chain.height
    block_timestamp = datetime.fromtimestamp(chain[block_id].timestamp, tz=timezone.utc)
    total_supply = nft_contract.totalSupply(block_identifier=block_id)

    # hopefully faster with multicall
    with brownie.multicall(block_identifier=block_id):
        owners = [nft_contract.ownerOf(i) for i in range(0, total_supply)]

    # count per owner address
    owners = dict()
    for addr in owners:
        owners[addr] = owners.get(addr, 0) + 1

    # sort by address
    owners = dict(sorted(owners.items(), key=lambda x: x[0]))

    snapshots = Path('snapshots')
    lobs_owners = snapshots/"lobs_owners"
    lobs_owners.mkdir(exist_ok=True)
    lobs_count_by_addr = snapshots/"lobs_count_by_addr"
    lobs_count_by_addr.mkdir(exist_ok=True)

    fn_suffix = f'{block_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")}_blk{block_id}'

    with open(lobs_owners/f"lobs-owners_{fn_suffix}.txt", 'w') as f:
        f.write('\n'.join(owners.keys()) + '\n')

    with open(lobs_count_by_addr/f"lobs-count-by-addr_{fn_suffix}.csv", 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['address', 'count'])
        writer.writerows(owners.items())

    files = [f.stem for f in lobs_owners.glob('lobs-owners_*_blk*.txt')] + [f.stem for f in lobs_count_by_addr.glob('lobs-count-by-addr_*_blk*.csv')]
    blkids_dates = sorted(
                set(
                    (int(part[1].partition('blk')[-1]), part[0])
                    for fn in files for part in fn.split('_')),
                key=lambda x: x[0],
                reverse=True)

    # honestly, whatever, i'll figure something out later
    with open('main/public/index.html', 'w') as f:
        f.write('<html><body><h1>lobs holders snapshots</h1><ul>')

        for blkid, date in blkids_dates:
            owners_files = list(lobs_owners.glob(f'*_blk{blkid}.txt'))
            count_by_addr_files = list(lobs_count_by_addr.glob(f'*_blk{blkid}.csv'))
            owners_link = f'<a href="{github_repo_raw_path + owners_files[0]}">lobs owners</a>' if len(owners_files) == 1 else "lobs owners"
            count_by_addr_link = f'<a href="{github_repo_raw_path + count_by_addr_files[0]}">lobs count by addr</a>' if len(count_by_addr_files) == 1 else "lobs count by addr"
            f.write(f'<li>{date}, block {blkid}: {owners_link}, {count_by_addr_link}</li>')

        f.write('</ul></body></html>')


if __name__ == '__main__':
    print("Build start...")

    main()

    print("Done?")
