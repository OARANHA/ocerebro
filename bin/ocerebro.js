#!/usr/bin/env node
/**
 * OCerebro CLI - Node.js wrapper
 *
 * Este script chama a CLI Python do OCerebro.
 * Usa CommonJS para compatibilidade máxima.
 */

const { execSync, spawn } = require('child_process');
const path = require('path');

// Determina o comando Python
function getPythonCmd() {
    try {
        // Tenta python primeiro
        execSync('python --version', { stdio: 'ignore' });
        return 'python';
    } catch {
        try {
            // Tenta python3
            execSync('python3 --version', { stdio: 'ignore' });
            return 'python3';
        } catch {
            console.error('Erro: Python não encontrado. Por favor instale Python 3.10+');
            process.exit(1);
        }
    }
}

// Encontra o caminho do pacote ocerebro
function getOcerebroPath() {
    try {
        // Tenta encontrar via pip show
        const output = execSync(`${getPythonCmd()} -m pip show ocerebro`, { encoding: 'utf-8' });
        const match = output.match(/Location: (.+)/);
        if (match) {
            return path.join(match[1].trim(), 'ocerebro');
        }
    } catch {
        // Se não estiver instalado via pip, usa path relativo
        return path.join(__dirname, '..');
    }
    return path.join(__dirname, '..');
}

// Argumentos da linha de comando
const args = process.argv.slice(2);

// Comando principal
const pythonCmd = getPythonCmd();
const ocerebroPath = getOcerebroPath();
const cliScript = path.join(ocerebroPath, 'src', 'cli', 'main.py');

// Executa a CLI Python
const pythonArgs = [cliScript, ...args];

const proc = spawn(pythonCmd, pythonArgs, {
    stdio: 'inherit',
    cwd: process.cwd()
});

proc.on('close', (code) => {
    process.exit(code);
});

proc.on('error', (err) => {
    console.error('Erro ao executar OCerebro:', err.message);
    process.exit(1);
});
