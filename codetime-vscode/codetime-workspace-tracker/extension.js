const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const logic = require('./tracker_logic.js');

const EVENT_URL = 'http://127.0.0.1:47625/tracker/event';
const shouldSend = logic.makeThrottle(15000);
let output;

function log(message) {
    if (output) {
        output.appendLine(
            `[${new Date().toLocaleTimeString()}] ${message}`
        );
    }
    console.log(`CodeTime: ${message}`);
}

function readToken() {
    try {
        const file = logic.tokenPath(process.env, os.homedir());
        const token = fs.readFileSync(file, 'utf8').trim();

        if (!token) {
            log('ERROR: Token file is empty.');
            return null;
        }

        return token;
    } catch (error) {
        log(`ERROR: Cannot read token: ${error.message}`);
        return null;
    }
}

async function sendActivity() {
    const folders = vscode.workspace.workspaceFolders;

    if (!folders || folders.length === 0) {
        log('Waiting: no workspace folder is open.');
        return;
    }

    const token = readToken();
    if (!token || !shouldSend(Date.now())) {
        return;
    }

    const event = logic.buildEvent(
        folders[0].uri.fsPath,
        new Date()
    );

    log(`Sending activity for project "${event.project}".`);

    try {
        const response = await fetch(EVENT_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CodeTime-Token': token
            },
            body: JSON.stringify(event)
        });

        const body = await response.text();

        if (!response.ok) {
            log(`ERROR: HTTP ${response.status}: ${body}`);
            return;
        }

        log(`Activity accepted: HTTP ${response.status}: ${body}`);
    } catch (error) {
        log(`ERROR: Cannot reach CodeTime server: ${error.message}`);
    }
}

function activate(context) {
    output = vscode.window.createOutputChannel('CodeTime Tracker');
    context.subscriptions.push(output);

    log('Extension activated.');

    context.subscriptions.push(
        vscode.commands.registerCommand(
            'codetime-workspace-tracker.showWorkspace',
            () => {
                const folders = vscode.workspace.workspaceFolders;

                if (!folders || folders.length === 0) {
                    vscode.window.showWarningMessage(
                        'CodeTime: No project folder is currently open.'
                    );
                    return;
                }

                vscode.window.showInformationMessage(
                    `CodeTime project folder: ${folders[0].uri.fsPath}`
                );
            }
        ),

        vscode.commands.registerCommand(
            'codetime-workspace-tracker.helloWorld',
            () => vscode.window.showInformationMessage(
                'Hello World from CodeTime Workspace Tracker!'
            )
        ),

        vscode.workspace.onDidChangeTextDocument(
            () => void sendActivity()
        ),

        vscode.window.onDidChangeActiveTextEditor(
            () => void sendActivity()
        ),

        vscode.window.onDidChangeTextEditorSelection(
            () => void sendActivity()
        ),

        vscode.window.onDidChangeWindowState((state) => {
            if (state.focused) {
                void sendActivity();
            }
        }),

        vscode.workspace.onDidChangeWorkspaceFolders(
            () => void sendActivity()
        )
    );

    // Send an initial event after the extension starts.
    setTimeout(() => void sendActivity(), 1000);
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};
