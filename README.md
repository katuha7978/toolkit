# Cross-Chain Bridge Event Listener Toolkit

This repository contains a Python-based simulation of a critical component in a cross-chain bridge system: the event listener. This script is designed to monitor a smart contract on a source blockchain, detect specific events (e.g., `TokensLocked`), and simulate the corresponding action on a destination blockchain (e.g., minting equivalent tokens).

This tool is built to be robust, modular, and illustrative of the architectural patterns used in real-world decentralized applications.

## Concept

A cross-chain bridge allows users to transfer assets or data from one blockchain (e.g., Ethereum) to another (e.g., Polygon). A common mechanism is the "lock-and-mint" approach:

1.  **Lock:** A user deposits tokens into a bridge smart contract on the source chain. The contract locks these tokens and emits an event, such as `TokensLocked`, containing details of the transaction (sender, amount, destination chain).
2.  **Listen:** Off-chain services, called listeners or validators, constantly monitor the source chain for these `TokensLocked` events.
3.  **Verify & Relay:** Upon detecting an event, the listener verifies its legitimacy and relays the information to the destination chain.
4.  **Mint:** A corresponding bridge contract on the destination chain receives this information and mints an equivalent amount of "wrapped" tokens for the user.

This script simulates the **Listen** and **Relay** steps (steps 2 and 3). It is the backbone of the bridge, ensuring that assets locked on one chain are correctly represented on another.

## Code Architecture

The script is designed with a clear separation of concerns, organized into several key classes:

-   `CrossChainEventListener`: The main orchestrator. It manages the lifecycle of the listening process, coordinates between the other components, and contains the main polling loop.

-   `BlockchainConnector`: A reusable utility class responsible for all direct interactions with a blockchain node. It encapsulates the `web3.py` setup, connection logic, and contract object creation. The listener instantiates two of these: one for the source chain and one for the destination.

-   `StateDB`: A simple, file-based persistence layer. Its purpose is to keep track of which events have already been processed. This is crucial to prevent double-spending or duplicate minting if the listener service restarts.

-   `process_event` (method within `CrossChainEventListener`): This is the core of the event processor. It performs:
    1.  **Data Extraction:** Parses the event log to get relevant data.
    2.  **State Check:** Queries `StateDB` to ensure the event is new.
    3.  **Business Logic:** Validates the event data (e.g., checks if the target chain ID is correct).
    4.  **Action Simulation:** Logs a detailed message simulating the transaction that would be sent to the destination chain.
    5.  **State Update:** Marks the event as processed in `StateDB`.

## How it Works

The listener operates in a continuous loop:

1.  **Initialization:** The script starts by initializing the `CrossChainEventListener`, which in turn sets up `BlockchainConnector` instances for both source and destination chains and loads the `StateDB`.

2.  **Get Start Block:** It determines which block to start scanning from. On first run, this is the latest block; on restart, it could be the last block it successfully processed.

3.  **Polling:** The main loop begins. In each iteration, it does the following:
    a. Fetches the current latest block number from the source chain.
    b. If the latest block is newer than the last scanned block, it defines a block range to scan (e.g., `from_block = last_scanned + 1`, `to_block = latest`).
    c. It uses a `web3.py` filter to query the source chain's bridge contract for any `TokensLocked` events within that block range.

4.  **Processing:**
    a. If events are found, it iterates through each one.
    b. For each event, it calls `process_event()`.
    c. The processor checks if the event's transaction hash is in the `StateDB`. If so, it's skipped.
    d. If the event is new, it simulates the minting transaction on the destination chain and then adds the transaction hash to the `StateDB`.

5.  **Wait:** After scanning, the script waits for a configured interval (e.g., 15 seconds) before starting the next polling cycle. This prevents overwhelming the RPC node.

## Usage Example

### 1. Prerequisites

-   Python 3.8+
-   Access to RPC endpoints for two EVM-compatible chains (e.g., via Infura, Alchemy).

### 2. Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/your-username/toolkit.git
cd toolkit
pip install -r requirements.txt
```

### 3. Configuration

Open `script.py` and modify the `CONFIG` dictionary at the top of the file:

```python
CONFIG = {
    'source_chain': {
        'name': 'SourceChain-Goerli',
        'rpc_url': 'https://goerli.infura.io/v3/YOUR_INFURA_PROJECT_ID',
        'bridge_contract_address': '0x...SOURCE_CONTRACT_ADDRESS...',
        'bridge_contract_abi': '[]' # A mock ABI is included, no need to change for demo
    },
    'destination_chain': {
        'name': 'DestinationChain-Mumbai',
        'rpc_url': 'https://polygon-mumbai.infura.io/v3/YOUR_INFURA_PROJECT_ID',
        'bridge_contract_address': '0x...DESTINATION_CONTRACT_ADDRESS...',
    },
    # ... other settings
}
```

-   Replace `YOUR_INFURA_PROJECT_ID` with your actual ID.
-   Replace the `bridge_contract_address` placeholders with the addresses of the bridge contracts you want to monitor.

### 4. Running the Script

Execute the script from your terminal:

```bash
python script.py
```

### 5. Expected Output

The script will log its activities to the console. When it detects and processes a new event, you will see output similar to this:

```
2023-10-27 14:30:00 - [INFO] - Successfully connected to SourceChain-Goerli at https://goerli.infura.io/v3/.... Chain ID: 5
2023-10-27 14:30:01 - [INFO] - Successfully connected to DestinationChain-Mumbai at https://polygon-mumbai.infura.io/v3/.... Chain ID: 80001
2023-10-27 14:30:01 - [INFO] - StateDB initialized. Loaded 0 processed transaction hashes from 'processed_events.json'.
2023-10-27 14:30:02 - [INFO] - Starting from the latest block: 9876543
2023-10-27 14:30:02 - [INFO] - Starting event listener for contract 0x...SOURCE_CONTRACT_ADDRESS...
...
2023-10-27 14:30:18 - [INFO] - Scanning blocks from 9876544 to 9876545...
2023-10-27 14:30:19 - [INFO] - Found new 'TokensLocked' event in transaction 0xabc123...
2023-10-27 14:30:19 - [INFO] - Processing lock for 100.0 tokens from 0xSenderAddress...
2023-10-27 14:30:20 - [INFO] - (Oracle) Suggested gas price on Mainnet: 25 Gwei

------------------------------------------------------------
2023-10-27 14:30:20 - [INFO] - SIMULATION: Triggering 'mint' on DestinationChain-Mumbai bridge contract. Recipient: 0xSenderAddress..., Amount: 100000000000000000000
------------------------------------------------------------

2023-10-27 14:30:20 - [INFO] - Transaction 0xabc123... marked as processed.
```
