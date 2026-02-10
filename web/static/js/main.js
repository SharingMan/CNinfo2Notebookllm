const stockInput = document.getElementById('stockInput');
const startBtn = document.getElementById('startBtn');
const progressSection = document.getElementById('progressSection');
const resultSection = document.getElementById('resultSection');
const terminal = document.getElementById('terminal');
const progressBar = document.getElementById('progressBar');
const progressPercent = document.getElementById('progressPercent');
const statusText = document.getElementById('statusText');
const notebookLink = document.getElementById('notebookLink');
const searchSuggestions = document.getElementById('searchSuggestions');

let eventSource = null;
let searchDebounceTimer = null;
let selectedSuggestionIndex = -1;
let currentSuggestions = [];

function setInput(val) {
    stockInput.value = val;
}

function addLog(msg, type = 'info') {
    const line = document.createElement('div');
    line.className = `terminal-line ${type}`;
    line.textContent = `> ${msg}`;
    terminal.appendChild(line);
    terminal.scrollTop = terminal.scrollHeight;
}

function updateProgress(percent, status) {
    progressBar.style.width = `${percent}%`;
    progressPercent.textContent = `${percent}%`;
    if (status) statusText.textContent = status;
}

async function startAnalysis() {
    const input = stockInput.value.trim();
    if (!input) {
        alert('请输入股票代码或名称');
        return;
    }

    // Reset UI
    terminal.innerHTML = '';
    progressSection.classList.remove('hidden');
    resultSection.classList.add('hidden');
    startBtn.disabled = true;
    startBtn.querySelector('.btn-text').textContent = '分析中...';
    startBtn.querySelector('.btn-loader').style.display = 'block';
    updateProgress(0, '正在连接服务器...');

    // Close existing connection
    if (eventSource) eventSource.close();

    // Start SSE connection
    eventSource = new EventSource(`/api/analyze?stock=${encodeURIComponent(input)}`);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        if (data.type === 'log') {
            addLog(data.message, data.level);
        } else if (data.type === 'progress') {
            updateProgress(data.percent, data.status);
        } else if (data.type === 'complete') {
            handleComplete(data);
        } else if (data.type === 'error') {
            handleError(data.message);
        }
    };

    eventSource.onerror = (err) => {
        console.error('SSE Error:', err);
        handleError('与服务器连接中断');
        eventSource.close();
    };
}

function handleComplete(data) {
    updateProgress(100, '获取完成！');
    addLog('所有资料已成功已下载到本地。', 'success');
    addLog(`存储路径: ${data.folder_path}`, 'success');

    setTimeout(() => {
        progressSection.classList.add('hidden');
        resultSection.classList.remove('hidden');

        const linkElem = document.getElementById('notebookLink');
        linkElem.textContent = "下载资料包 📦";
        linkElem.href = "#";
        linkElem.onclick = async (e) => {
            e.preventDefault();
            // Trigger download
            window.open(`/api/download-zip?path=${encodeURIComponent(data.folder_path)}`, '_blank');

            // Show message
            addLog('ZIP下载已开始，完成后云端文件将自动清理...', 'info');

            // Wait and then cleanup
            setTimeout(async () => {
                try {
                    await fetch(`/api/cleanup?path=${encodeURIComponent(data.folder_path)}`);
                    addLog('云端文件已清理', 'success');
                } catch (err) {
                    console.error('Cleanup error:', err);
                }
            }, 10000); // Cleanup after 10 seconds
        };
        linkElem.target = null;

        document.getElementById('resultDetails').innerHTML = `已经为 <b>${data.stock_name}</b> 准备好资料包。<br><br>
        📦 点击下方按钮下载 ZIP 压缩包<br>
        ⚠️ 下载完成后云端文件将自动清理以节省空间<br><br>
        内容包含：5年年报、最新季报、半年公告、及其 AI 分析指令。`;

        startBtn.disabled = false;
        startBtn.querySelector('.btn-text').textContent = '开始分析';
        startBtn.querySelector('.btn-loader').style.display = 'none';
    }, 1000);

    eventSource.close();
}

function handleError(msg) {
    addLog(`错误: ${msg}`, 'error');
    statusText.textContent = '任务失败';
    startBtn.disabled = false;
    startBtn.querySelector('.btn-text').textContent = '开始分析';
    startBtn.querySelector('.btn-loader').style.display = 'none';
    eventSource.close();
}

function resetUI() {
    resultSection.classList.add('hidden');
    progressSection.classList.add('hidden');
    stockInput.value = '';
}

startBtn.addEventListener('click', startAnalysis);

stockInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        if (selectedSuggestionIndex >= 0 && currentSuggestions.length > 0) {
            selectSuggestion(currentSuggestions[selectedSuggestionIndex]);
        } else {
            startAnalysis();
        }
    }
});

// Fuzzy Search
async function performSearch(query) {
    if (!query || query.length < 1) {
        hideSuggestions();
        return;
    }

    try {
        const response = await fetch(`/api/search?query=${encodeURIComponent(query)}&limit=10`);
        const data = await response.json();

        if (data.results && data.results.length > 0) {
            showSuggestions(data.results);
        } else {
            hideSuggestions();
        }
    } catch (err) {
        console.error('Search error:', err);
        hideSuggestions();
    }
}

// Market name mapping
const MARKET_NAMES = {
    'szse': 'A股',
    'sse': 'A股',
    'hke': '港股',
    'bond': '债券',
    'fund': '基金',
    'US': '美股'
};

function showSuggestions(results) {
    currentSuggestions = results;
    selectedSuggestionIndex = -1;

    searchSuggestions.innerHTML = results.map((item, index) => {
        const marketName = MARKET_NAMES[item.market] || item.market;
        return `
        <div class="search-suggestion-item" data-index="${index}" data-code="${item.code}">
            <div class="suggestion-info">
                <span class="suggestion-code">${item.code}</span>
                <span class="suggestion-name">${item.name}</span>
            </div>
            <span class="suggestion-market">${marketName}</span>
        </div>
    `}).join('');

    searchSuggestions.classList.remove('hidden');

    // Add click handlers
    searchSuggestions.querySelectorAll('.search-suggestion-item').forEach((el, index) => {
        el.addEventListener('click', () => selectSuggestion(results[index]));
        el.addEventListener('mouseenter', () => {
            selectedSuggestionIndex = index;
            updateActiveSuggestion();
        });
    });
}

function hideSuggestions() {
    searchSuggestions.classList.add('hidden');
    selectedSuggestionIndex = -1;
    currentSuggestions = [];
}

function selectSuggestion(item) {
    stockInput.value = item.code;
    hideSuggestions();
    startAnalysis();
}

function updateActiveSuggestion() {
    searchSuggestions.querySelectorAll('.search-suggestion-item').forEach((el, index) => {
        el.classList.toggle('active', index === selectedSuggestionIndex);
    });
}

// Input event for fuzzy search
stockInput.addEventListener('input', (e) => {
    const query = e.target.value.trim();

    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
        performSearch(query);
    }, 200);
});

// Keyboard navigation
stockInput.addEventListener('keydown', (e) => {
    if (currentSuggestions.length === 0) return;

    if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedSuggestionIndex = Math.min(selectedSuggestionIndex + 1, currentSuggestions.length - 1);
        updateActiveSuggestion();
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedSuggestionIndex = Math.max(selectedSuggestionIndex - 1, -1);
        updateActiveSuggestion();
    } else if (e.key === 'Escape') {
        hideSuggestions();
    }
});

// Hide suggestions when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.search-wrapper')) {
        hideSuggestions();
    }
});
