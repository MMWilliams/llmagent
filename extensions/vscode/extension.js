// Sample VSCode extension code for LLMAgent integration
const vscode = require('vscode');
const axios = require('axios');
const path = require('path');
const fs = require('fs');

let apiBaseUrl = 'http://localhost:8000';
let currentWorkspaceId = null;

/**
 * Activate the extension
 */
function activate(context) {
    console.log('LLMAgent extension is now active');

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('llmagent.initialize', initializeAgent),
        vscode.commands.registerCommand('llmagent.runPrompt', runPrompt),
        vscode.commands.registerCommand('llmagent.viewStatus', viewStatus),
        vscode.commands.registerCommand('llmagent.approveAction', approveAction),
        vscode.commands.registerCommand('llmagent.rejectAction', rejectAction)
    );

    // Create status bar item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = "$(robot) LLMAgent";
    statusBarItem.command = 'llmagent.viewStatus';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Set configuration
    const config = vscode.workspace.getConfiguration('llmagent');
    apiBaseUrl = config.get('apiUrl') || apiBaseUrl;
}

/**
 * Initialize a new agent
 */
async function initializeAgent() {
    try {
        const modelType = await vscode.window.showQuickPick(['llamacpp', 'transformers'], {
            placeHolder: 'Select model type'
        });

        if (!modelType) return;

        const modelId = await vscode.window.showInputBox({
            placeHolder: 'Enter model ID (optional)'
        });

        // Create new agent
        const response = await axios.post(`${apiBaseUrl}/agents`, {
            model_type: modelType,
            model_id: modelId || undefined
        });

        currentWorkspaceId = response.data.workspace_id;

        vscode.window.showInformationMessage(`Agent initialized with workspace ID: ${currentWorkspaceId}`);
    } catch (error) {
        vscode.window.showErrorMessage(`Error initializing agent: ${error.message}`);
    }
}

/**
 * Run a prompt with the agent
 */
async function runPrompt() {
    try {
        if (!currentWorkspaceId) {
            const initializeFirst = await vscode.window.showQuickPick(['Yes', 'No'], {
                placeHolder: 'No agent initialized. Initialize a new agent?'
            });

            if (initializeFirst === 'Yes') {
                await initializeAgent();
            } else {
                return;
            }
        }

        // Get prompt
        const prompt = await vscode.window.showInputBox({
            placeHolder: 'Enter prompt for the agent'
        });

        if (!prompt) return;

        // Get mode
        const mode = await vscode.window.showQuickPick(['approval', 'autonomous'], {
            placeHolder: 'Select agent mode'
        });

        if (!mode) return;

        // Run prompt
        const response = await axios.post(`${apiBaseUrl}/agents/${currentWorkspaceId}/prompt`, {
            prompt,
            mode
        });

        if (mode === 'approval' && response.data.pending_actions && response.data.pending_actions.length > 0) {
            // Show actions for approval
            for (const actionData of response.data.pending_actions) {
                await showActionApprovalDialog(actionData);
            }
        } else {
            vscode.window.showInformationMessage(`Agent is running in ${mode} mode.`);
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Error running prompt: ${error.message}`);
    }
}

/**
 * Show a dialog for action approval
 */
async function showActionApprovalDialog(actionData) {
    const action = actionData.action;
    
    // Format action for display
    let message = `Action: ${action.type}\n`;
    
    if (action.params) {
        for (const [key, value] of Object.entries(action.params)) {
            const displayValue = typeof value === 'string' && value.length > 50
                ? value.substring(0, 50) + '...'
                : value;
            message += `${key}: ${displayValue}\n`;
        }
    }
    
    // Show complete action details in WebView for complex actions
    if (action.type === 'write_file' || action.type === 'run_code') {
        const panel = vscode.window.createWebviewPanel(
            'actionDetails',
            `Action: ${action.type}`,
            vscode.ViewColumn.One,
            { enableScripts: true }
        );
        
        let content = '';
        
        if (action.type === 'write_file') {
            const fileContent = action.params.content || '';
            content = `<h2>File: ${action.params.filepath}</h2><pre>${escapeHtml(fileContent)}</pre>`;
        } else if (action.type === 'run_code') {
            const code = action.params.code || '';
            content = `<h2>Code to Execute:</h2><pre>${escapeHtml(code)}</pre>`;
        }
        
        panel.webview.html = `
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Action Details</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                pre { background: #f4f4f4; padding: 10px; overflow: auto; }
            </style>
        </head>
        <body>
            <h1>Action Details</h1>
            ${content}
            
            <div style="margin-top: 20px;">
                <button id="approve">Approve</button>
                <button id="reject">Reject</button>
            </div>
            
            <script>
                const vscode = acquireVsCodeApi();
                document.getElementById('approve').addEventListener('click', () => {
                    vscode.postMessage({ command: 'approve' });
                });
                document.getElementById('reject').addEventListener('click', () => {
                    vscode.postMessage({ command: 'reject' });
                });
            </script>
        </body>
        </html>
        `;
        
        // Handle messages from webview
        panel.webview.onDidReceiveMessage(async message => {
            if (message.command === 'approve') {
                await approveAction(actionData.id);
                panel.dispose();
            } else if (message.command === 'reject') {
                await rejectAction(actionData.id);
                panel.dispose();
            }
        });
    } else {
        // Simple dialog for other actions
        const choice = await vscode.window.showInformationMessage(
            message,
            { modal: true },
            'Approve',
            'Reject'
        );
        
        if (choice === 'Approve') {
            await approveAction(actionData.id);
        } else if (choice === 'Reject') {
            await rejectAction(actionData.id);
        }
    }
}

/**
 * Approve an action
 */
async function approveAction(actionId) {
    try {
        const response = await axios.post(`${apiBaseUrl}/agents/${currentWorkspaceId}/actions/${actionId}`, {
            approved: true
        });
        
        if (response.data.status === 'executed') {
            vscode.window.showInformationMessage('Action executed successfully.');
            
            // If it was a file write action, refresh the explorer
            if (response.data.result && response.data.result.filepath) {
                vscode.commands.executeCommand('workbench.files.action.refreshFilesExplorer');
            }
        }
    } catch (error) {
        vscode.window.showErrorMessage(`Error approving action: ${error.message}`);
    }
}

/**
 * Reject an action
 */
async function rejectAction(actionId) {
    try {
        await axios.post(`${apiBaseUrl}/agents/${currentWorkspaceId}/actions/${actionId}`, {
            approved: false
        });
        
        vscode.window.showInformationMessage('Action rejected.');
    } catch (error) {
        vscode.window.showErrorMessage(`Error rejecting action: ${error.message}`);
    }
}

/**
 * View agent status
 */
async function viewStatus() {
    try {
        if (!currentWorkspaceId) {
            vscode.window.showInformationMessage('No agent is currently initialized.');
            return;
        }
        
        const response = await axios.get(`${apiBaseUrl}/agents/${currentWorkspaceId}/status`);
        
        // Create a WebView to show detailed status
        const panel = vscode.window.createWebviewPanel(
            'agentStatus',
            'LLMAgent Status',
            vscode.ViewColumn.One,
            { enableScripts: true }
        );
        
        const statusData = response.data;
        const progress = statusData.progress;
        
        let progressHtml = '';
        if (progress) {
            const percentage = Math.floor((progress.progress / progress.total_steps) * 100);
            progressHtml = `
            <div class="progress-bar">
                <div class="progress" style="width: ${percentage}%"></div>
            </div>
            <p>${progress.progress} / ${progress.total_steps} (${percentage}%)</p>
            `;
        }
        
        panel.webview.html = `
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Agent Status</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 20px; }
                .status-box { background: #f4f4f4; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                .progress-bar { background: #e0e0e0; height: 20px; border-radius: 10px; overflow: hidden; }
                .progress { background: #4CAF50; height: 100%; }
                table { border-collapse: collapse; width: 100%; }
                th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
                th { background-color: #f2f2f2; }
            </style>
        </head>
        <body>
            <h1>LLMAgent Status</h1>
            
            <div class="status-box">
                <h2>Current Status: ${statusData.agent_status}</h2>
                <p>Workspace ID: ${statusData.workspace_id}</p>
                <p>Current Iteration: ${statusData.iteration}</p>
                
                <h3>Progress</h3>
                ${progressHtml}
            </div>
            
            <button id="refresh">Refresh Status</button>
            
            <script>
                const vscode = acquireVsCodeApi();
                document.getElementById('refresh').addEventListener('click', () => {
                    vscode.postMessage({ command: 'refresh' });
                });
            </script>
        </body>
        </html>
        `;
        
        // Handle messages from webview
        panel.webview.onDidReceiveMessage(message => {
            if (message.command === 'refresh') {
                viewStatus();
                panel.dispose();
            }
        });
    } catch (error) {
        vscode.window.showErrorMessage(`Error getting agent status: ${error.message}`);
    }
}

/**
 * Helper to escape HTML
 */
function escapeHtml(unsafe) {
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/**
 * Deactivate the extension
 */
function deactivate() {
    console.log('LLMAgent extension is now deactivated');
}

module.exports = {
    activate,
    deactivate
};