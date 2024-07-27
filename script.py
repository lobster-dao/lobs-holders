#!/usr/bin/env python3.8
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import os

from web3 import Web3, HTTPProvider

github_repo_raw_path = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/raw/'
rpc_url = f"https://cloudflare-eth.com/"
multicall_chunk_size = 250
snapshots_limit = 5000

codec = Web3().codec

w3 = Web3(HTTPProvider(rpc_url))
with open('abis/LobstersNft.json', 'r') as f:
    lobs_abi = json.load(f)
with open('abis/Multicall2.json', 'r') as f:
    mc2_abi = json.load(f)
lobs_contract = w3.eth.contract('0x026224A2940bFE258D0dbE947919B62fE321F042', abi=lobs_abi)
mc2_contract = w3.eth.contract('0x5BA1e12693Dc8F9c48aAD8770482f4739bEeD696', abi=mc2_abi)
first_block = 13378748 # block at which contract was deployed

snapshots_dir = Path('snapshots')
lobs_owners_dir = snapshots_dir/"lobs_owners"
lobs_owners_dir.mkdir(exist_ok=True)
lobs_count_dir = snapshots_dir/"lobs_count_by_addr"
lobs_count_dir.mkdir(exist_ok=True)

def gen_calls(calls):
    to_send = list()
    for call in calls:
        args = tuple(arg['type'] for arg in call.abi['inputs'])
        selector = Web3.keccak(text = f"{call.abi['name']}({','.join(args)})")[0:4]
        argdata = codec.encode_abi(args, call.args)
        to_send.append((call.address, selector + argdata))
    return to_send

def parse_results(calls, results):
    ret = list()
    for idx, (success, data) in enumerate(results):
        if not success:
            ret.append(None)
        else:
            types = tuple(arg['type'] for arg in calls[idx].abi['outputs'])
            dec_raw = codec.decode_abi(types, data)
            decoded = tuple(Web3.toChecksumAddress(d) if t == 'address' else d for t, d in zip(types, dec_raw))
            ret.append(decoded[0] if len(decoded) == 1 else decoded)
    return ret

def multicall(mc2_contract, calls, block_identifier='latest'):
    to_send = gen_calls(calls)
    res = mc2_contract.functions.tryAggregate(False, to_send).call(block_identifier=block_identifier)
    return parse_results(calls, res)

def get_holders(block_identifier='latest'):
    if block_identifier == 'latest': # for consistent results
        block_id = w3.eth.blockNumber
    else:
        block_id = block_identifier

    print(f"Using block {block_id}")

    total_supply = lobs_contract.functions.totalSupply().call(block_identifier=block_id)
    print(f"Current LOBS supply is {total_supply}\n")

    owners_list = list()
    calls = [lobs_contract.functions.ownerOf(i) for i in range(0, total_supply)]
    print(f"Getting owners with multicall chunk size {multicall_chunk_size}...")
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = list()
        for i in range(0, len(calls), multicall_chunk_size):
            def func(start_idx):
                chunk = calls[start_idx:start_idx+multicall_chunk_size]
                res = multicall(mc2_contract, chunk, block_identifier=block_id)
                print(f"Done for IDs {start_idx}..{start_idx + len(chunk) - 1}")
                return res
            futures.append(executor.submit(func, i))

        # ideally sequential so owners_list[nft_id] is the owner of nft #nft_id
        for fut in futures:
            owners_list.extend(fut.result())
    print(f"All done, {len(owners_list)} total\n")

    print(f"Making a list, checking it twice")
    # count per owner address
    owners = dict()
    for addr_raw in owners_list:
        addr = str(addr_raw)
        owners[addr] = owners.get(addr, 0) + 1

    # sort by address
    owners = dict(sorted(owners.items(), key=lambda x: x[0]))
    return owners

def save_holders(block_identifier='latest'):
    block = w3.eth.getBlock(block_identifier)
    block_id = block.number
    block_timestamp = datetime.fromtimestamp(block.timestamp, tz=timezone.utc)
    print(f"Selected block is {block_id}, timestamp {block_timestamp}")

    owners = get_holders(block_id)

    fn_suffix = f'{block_timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")}_blk{block_id}'

    lobs_owners_file = lobs_owners_dir/f"lobs-owners_{fn_suffix}.txt"
    print(f"Writing owners list to {lobs_owners_file}")
    with open(lobs_owners_file, 'w') as f:
        f.write('\n'.join(owners.keys()) + '\n')

    lobs_count_by_addr_file = lobs_count_dir/f"lobs-count-by-addr_{fn_suffix}.csv"
    print(f"Writing LOBS count by addr list to {lobs_count_by_addr_file}")
    with open(lobs_count_by_addr_file, 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['address', 'count'])
        writer.writerows(owners.items())

def get_snapshots():
    def parse(filenames):
        snapshots = set() # (blk_num, timestamp)
        for fn in filenames:
            parts = fn.split('_')
            snapshots.add((int(parts[2].partition('blk')[-1]), parts[1]))
        return snapshots


    snapshots_owners = parse(f.stem for f in lobs_owners_dir.glob('lobs-owners_*_blk*.txt'))
    snapshots_counts = parse(f.stem for f in lobs_count_dir.glob('lobs-count-by-addr_*_blk*.csv'))

    return snapshots_owners.intersection(snapshots_counts)

def write_index():
    snapshots = sorted(get_snapshots(), key=lambda x: x[0], reverse=True)
    print(f"We have {len(snapshots)} past snapshots; will include {min(len(snapshots), snapshots_limit)} in index")

    # honestly, whatever, i'll figure something out later
    public = Path('public')
    public.mkdir(exist_ok=True)
    print(f"Writing index...")
    with open(public/'index.html', 'w') as f:
        f.write('<html><body><h1>lobs holders snapshots</h1><ul>')

        for blkid, date in snapshots[0:snapshots_limit]:
            owners_files = list(lobs_owners_dir.glob(f'*_blk{blkid}.txt'))
            count_by_addr_files = list(lobs_count_dir.glob(f'*_blk{blkid}.csv'))
            owners_link = f'<a href="{github_repo_raw_path + str(owners_files[0])}">lobs owners</a>' if len(owners_files) == 1 else "lobs owners"
            count_by_addr_link = f'<a href="{github_repo_raw_path + str(count_by_addr_files[0])}">lobs count by addr</a>' if len(count_by_addr_files) == 1 else "lobs count by addr"
            f.write(f'<li>{date}, block {blkid}: {owners_link}, {count_by_addr_link}</li>')

        f.write('</ul></body></html>')

def main(block_identifier=None, build_index=True):
    def save_holders_with_retry(block_identifier):
        tries = 3
        while True:
            try:
                tries -= 1
                save_holders(block_identifier)
            except ValueError as e:
                if tries <= 0:
                    raise
                else:
                    print(f"Something went wrong, trying again (tries left = {tries})")
            else:
                break

    if block_identifier == None: # default behavior: snapshots every 1k blocks + backfill if needed
        snapshots_blkids = {x[0] for x in filter(lambda y: y[0] % 1000 == 0, get_snapshots())}
        latest = (w3.eth.blockNumber - 5) // 1000 * 1000 # in case of reorgs
        expected_count = (latest - first_block) // 1000 + 1
        current = latest
        print(f"We have {len(snapshots_blkids)} now; expecting {expected_count} snapshots")
        build_index = build_index and expected_count != len(snapshots_blkids) # skip building index if we're already caught up
        while len(snapshots_blkids) < expected_count:
            assert current >= first_block, f"attempting to get holders for block {current}, which is before first block {first_block}" # should never happen

            if current not in snapshots_blkids:
                save_holders_with_retry(current)
                snapshots_blkids.add(current)
            current -= 1000
    else:
        save_holders_with_retry(block_identifier)

    if build_index:
        write_index()

if __name__ == '__main__':
    print("Starting build\n")
    main()
    print("\nDone?")
