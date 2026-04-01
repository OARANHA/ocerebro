#!/usr/bin/env node
/**
 * OCerebro CLI - Node.js wrapper
 *
 * Este script chama a CLI Python do OCerebro.
 * Usa CommonJS para compatibilidade máxima.
 */

const { execSync, spawn } = require('child_process');
const path = require('path');

// Determina o comando Python e valida versão
function getPythonCmd() {
    const candidates = [];

    // Tenta python primeiro
    try {
        execSync('python --version', { stdio: 'ignore' });
        candidates.push('python');
    } catch {
        // Tenta python3
        try {
            execSync('python3 --version', { stdio: 'ignore' });
            candidates.push('python3');
        } catch {
            console.error('Erro: Python não encontrado. Por favor instale Python 3.10+');
            process.exit(1);
        }
    }

    // Valida versão do Python
    for (const cmd of candidates) {
        try {
            const versionOutput = execSync(`${cmd} --version`, {
                encoding: 'utf-8',
                stdio: ['ignore', 'pipe', 'pipe']
            });
            const match = versionOutput.match(/Python (\d+)\.(\d+)/);
            if (match) {
                const major = parseInt(match[1]);
                const minor = parseInt(match[2]);
                if (major < 3 || (major === 3 && minor < 10)) {
                    console.error(`❌ Python ${major}.${minor} detectado.`);
                    console.error('   OCerebro requer Python 3.10+');
                    console.error('   Baixe em: https://python.org');
                    process.exit(1);
                }
                return cmd;
            }
        } catch (err) {
            continue;
        }
    }

    // Fallback para o primeiro candidato
    return candidates[0];
}

// Encontra o caminho do pacote ocerebro
function getOcerebroPath(pythonCmd) {
    try {
        // Usa -c para obter o path real do módulo instalado
        const output = execSync(
            `${pythonCmd} -c "import src.cli.main; import os; print(os.path.dirname(os.path.dirname(os.path.dirname(src.cli.main.__file__))))"`,
            { encoding: 'utf-8' }
        );
        return output.trim();
    } catch {
        // Fallback: usa pip show para encontrar o Location
        try {
            const pipOutput = execSync(`${pythonCmd} -m pip show ocerebro`, { encoding: 'utf-8' });
            const match = pipOutput.match(/Location: (.+)/);
            if (match) {
                return match[1].trim(); // sem subpasta "ocerebro/"
            }
        } catch {
            // Se não estiver instalado via pip, usa path relativo ao bin/
            return path.join(__dirname, '..');
        }
    }
    return path.join(__dirname, '..');
}

// Argumentos da linha de comando
const args = process.argv.slice(2);

// Comando principal (chamado UMA única vez)
const pythonCmd = getPythonCmd();
const ocerebroPath = getOcerebroPath(pythonCmd);
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
