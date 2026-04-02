#!/usr/bin/env node
/**
 * OCerebro CLI - Node.js wrapper (zero-friction)
 * Instala automaticamente o pacote Python se necessário.
 */

const { execSync, execFileSync, spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

// ── 1. Encontra Python 3.10+ no sistema ──────────────────────────────────────
function getPythonCmd() {
    const candidates = ['python', 'python3', 'python3.12', 'python3.11', 'python3.10'];

    for (const cmd of candidates) {
        try {
            const out = execSync(`${cmd} --version`, {
                encoding: 'utf-8',
                stdio: ['ignore', 'pipe', 'pipe']
            });
            const m = out.match(/Python (\d+)\.(\d+)/);
            if (m) {
                const [major, minor] = [parseInt(m[1]), parseInt(m[2])];
                if (major === 3 && minor >= 10) return cmd;
            }
        } catch (_) { continue; }
    }

    console.error('❌ Python 3.10+ não encontrado.');
    console.error('   Instale em: https://python.org/downloads');
    process.exit(1);
}

// ── 2. Garante que ocerebro está instalado via pip ────────────────────────────
function ensurePipPackage(pythonCmd) {
    try {
        execSync(`${pythonCmd} -c "import src.cli.main"`, { stdio: 'ignore' });
        return; // já instalado
    } catch (_) {}

    console.log('📦 Instalando ocerebro via pip...');
    try {
        execSync(`${pythonCmd} -m pip install ocerebro --quiet`, { stdio: 'inherit' });
    } catch (e) {
        console.error('❌ Falha ao instalar ocerebro via pip.');
        console.error('   Tente manualmente: pip install ocerebro');
        process.exit(1);
    }
}

// ── 3. Resolve path do main.py instalado ─────────────────────────────────────
function getCliScript(pythonCmd) {
    // Estratégia A: import direto (mais confiável)
    try {
        const out = execSync(
            `${pythonCmd} -c "import src.cli.main, os; print(src.cli.main.__file__)"`,
            { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] }
        );
        const p = out.trim();
        if (fs.existsSync(p)) return p;
    } catch (_) {}

    // Estratégia B: pip show Location
    try {
        const out = execSync(`${pythonCmd} -m pip show ocerebro`, { encoding: 'utf-8' });
        const m = out.match(/Location: (.+)/);
        if (m) {
            const p = path.join(m[1].trim(), 'src', 'cli', 'main.py');
            if (fs.existsSync(p)) return p;
        }
    } catch (_) {}

    // Estratégia C: path relativo ao bin/ (dev local)
    const localScript = path.join(__dirname, '..', 'src', 'cli', 'main.py');
    if (fs.existsSync(localScript)) return localScript;

    console.error('❌ Não foi possível localizar o CLI do ocerebro.');
    console.error('   Tente: pip install --force-reinstall ocerebro');
    process.exit(1);
}

// ── Main ──────────────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
const pythonCmd = getPythonCmd();
ensurePipPackage(pythonCmd);
const cliScript = getCliScript(pythonCmd);

const proc = spawn(pythonCmd, [cliScript, ...args], {
    stdio: 'inherit',
    cwd: process.cwd()
});

proc.on('close', (code) => process.exit(code ?? 0));
proc.on('error', (err) => {
    console.error('❌ Erro ao executar OCerebro:', err.message);
    process.exit(1);
});
