#!/usr/bin/env python3.8

import csv
import brownie

from brownie import Contract


def main():
    brownie.network.connect('mainnet')

    # lobsterdao, or plop your contract addr here
    nft_contract = Contract('0x026224a2940bfe258d0dbe947919b62fe321f042')
    total_supply = nft_contract.totalSupply()

    # hopefully faster with multicall
    with brownie.multicall:
        owners = [nft_contract.ownerOf(i) for i in range(0, total_supply)]

    # count num occurrences of each address, then sort in reverse order
    owner_addresses = set(owners)
    count_per_address = {addr: owners.count(addr) for addr in owner_addresses}
    count_per_address = dict(sorted(count_per_address.items(), key=lambda x: x[1], reverse=True))

    with open('nft_owners.csv', 'w') as f:
        writer = csv.writer(f)
        writer.writerow(['address', 'count'])
        writer.writerows(count_per_address.items())

    print('\n'.join([f"{addr}: {count}" for addr, count in count_per_address.items()]))

if __name__ == '__main__':
    main()
