const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const logic = require('./tracker_logic.js');

/**
 * Runs when the extension activates.
 * @param {vscode.ExtensionContext} context
 */
const EVENT_URL = 'http://127.0.0.1:47625/tracker/event';
const shouldSend = logic.makeThrottle(15000);

function readToken() {
    try {
        const file = logic.tokenPath(process.env, os.homedir());
        return fs.readFileSync(file, 'utf8').trim();
    } catch {
        return null;
    }
}

// Sends the folder NAME and a time. Never file contents or keystrokes.
async function sendActivity() {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        return;
    }
    if (!shouldSend(Date.now())) {
        return;
    }
    const token = readToken();
    if (!token) {
        return;
    }
    const event = logic.buildEvent(folders[0].uri.fsPath, new Date());
    try {
        await fetch(EVENT_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CodeTime-Token': token
            },
            body: JSON.stringify(event)
        });
    } catch {
        // CodeTime server not running: ignore, never interrupt editing.
    }
}

function startTracking(context) {
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument(sendActivity),
        vscode.window.onDidChangeActiveTextEditor(sendActivity),
        vscode.window.onDidChangeTextEditorSelection(sendActivity),
        vscode.window.onDidChangeWindowState((state) => {
            if (state.focused) {
                sendActivity();
            }
        })
    );
}

function activate(context) {
    console.log('CodeTime Workspace Tracker is now active.');

    const helloWorldCommand = vscode.commands.registerCommand(
        'codetime-workspace-tracker.helloWorld',
        () => {
            vscode.window.showInformationMessage(
                'Hello World from CodeTime Workspace Tracker!'
            );
        }
    );

    const showWorkspaceCommand = vscode.commands.registerCommand(
        'codetime-workspace-tracker.showWorkspace',
        () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;

            

            if (!workspaceFolders || workspaceFolders.length === 0) {
                vscode.window.showWarningMessage(
                    'CodeTime: No project folder is currently open.'
                );
                return;
            }

            const projectFolder = workspaceFolders[0].uri.fsPath;

            vscode.window.showInformationMessage(
                `CodeTime project folder: ${projectFolder}`
            );
        }
    );

    startTracking(context);

    context.subscriptions.push(
        helloWorldCommand,
        showWorkspaceCommand
    );
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};