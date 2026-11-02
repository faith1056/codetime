const vscode = require('vscode');

/**
 * Runs when the extension activates.
 * @param {vscode.ExtensionContext} context
 */
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