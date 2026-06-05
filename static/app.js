// --- GLOBAL APPLICATION STATE ---
let appState = null;
let binanceWs = null;
let latestPrices = {}; // Stores symbol -> price in-memory
let pendingAccountToSwitch = null;

// DOM Elements
const modeBadge = document.getElementById('modeBadge');
const modeLabel = document.getElementById('modeLabel');
const activeAccountSelect = document.getElementById('activeAccountSelect');
const botStatusToggle = document.getElementById('botStatusToggle');
const statusPulse = document.getElementById('statusPulse');

const metricTotalBalance = document.getElementById('metricTotalBalance');
const metricSafeBalance = document.getElementById('metricSafeBalance');
const metricFreeBalance = document.getElementById('metricFreeBalance');
const metricAllocatedCapital = document.getElementById('metricAllocatedCapital');
const metricRealizedPnL = document.getElementById('metricRealizedPnL');
const metricRealizedDesc = document.getElementById('metricRealizedDesc');
const metricUnrealizedPnL = document.getElementById('metricUnrealizedPnL');
const metricWinRate = document.getElementById('metricWinRate');
const metricWinRatio = document.getElementById('metricWinRatio');

const watchlistSelect = document.getElementById('watchlistSelect');
const addTokenInput = document.getElementById('addTokenInput');
const addTokenBtn = document.getElementById('addTokenBtn');
const watchlistList = document.getElementById('watchlistList');

const totalBalanceInput = document.getElementById('totalBalanceInput');
const totalBalanceGroup = document.getElementById('totalBalanceGroup');
const capitalSlider = document.getElementById('capitalSlider');
const capitalSliderVal = document.getElementById('capitalSliderVal');
const maxTradesSlider = document.getElementById('maxTradesSlider');
const maxTradesSliderVal = document.getElementById('maxTradesSliderVal');
const sheetsWebhookUrl = document.getElementById('sheetsWebhookUrl');
const saveSettingsBtn = document.getElementById('saveSettingsBtn');

const positionsList = document.getElementById('positionsList');
const terminalLogs = document.getElementById('terminalLogs');
const strategyStatusBody = document.getElementById('strategyStatusBody');
const historyTableBody = document.getElementById('historyTableBody');

const createAccountForm = document.getElementById('createAccountForm');
const accName = document.getElementById('accName');
const accMode = document.getElementById('accMode');
const accInitialBalance = document.getElementById('accInitialBalance');
const initialBalanceRow = document.getElementById('initialBalanceRow');
const accApiKey = document.getElementById('accApiKey');
const accApiSecret = document.getElementById('accApiSecret');
const credentialsWrapper = document.getElementById('credentialsWrapper');
const profilesList = document.getElementById('profilesList');

const stopWarningModal = document.getElementById('stopWarningModal');
const accountSwitchModal = document.getElementById('accountSwitchModal');
const confirmAccountSwitchBtn = document.getElementById('confirmAccountSwitchBtn');

const toastNotification = document.getElementById('toastNotification');
const toastIcon = document.getElementById('toastIcon');
const toastMsg = document.getElementById('toastMsg');

// --- INITIALIZE APPLICATION ---
// --- AUTO-SAVE & EXCHANGE STATUS LOGIC ---

// Auto-save on slider change (when user releases handle)
capitalSlider.addEventListener('change', () => {
  capitalSliderVal.innerText = `$${capitalSlider.value}`;
  handleSaveSettings();
});
maxTradesSlider.addEventListener('change', () => {
  maxTradesSliderVal.innerText = maxTradesSlider.value;
  handleSaveSettings();
});
// Auto-save on webhook URL blur
sheetsWebhookUrl.addEventListener('blur', handleSaveSettings);
// Auto-save on total balance input blur (paper mode)
if (totalBalanceInput) {
  totalBalanceInput.addEventListener('blur', handleSaveSettings);
}

// Helper to toggle credential fields visibility based on selected mode
function toggleCredentialFields() {
  if (accMode.value === 'real') {
    credentialsWrapper.classList.remove('hidden');
    initialBalanceRow.classList.add('hidden');
  } else {
    credentialsWrapper.classList.add('hidden');
    initialBalanceRow.classList.remove('hidden');
  }
}

// Fetch exchange status and update monitor card UI
async function fetchExchangeStatus(forceCheck = false) {
  const statusTitle  = document.getElementById('emStatusTitle');
  const statusSub    = document.getElementById('emStatusSub');
  const accountName  = document.getElementById('emAccountName');
  const exchangeName = document.getElementById('emExchangeName');
  const latency      = document.getElementById('emLatency');
  const stream       = document.getElementById('emStream');
  const detailMsg    = document.getElementById('emDetailMsg');
  const lastCheck    = document.getElementById('emLastCheck');
  const lightDot     = document.getElementById('emLightDot');

  // Guard: if any element is missing just bail (DOM not ready)
  if (!statusTitle || !lightDot || !detailMsg) return;

  // Show a subtle "Checking…" pulse while the request is in flight
  if (forceCheck) {
    statusTitle.innerText  = 'CHECKING…';
    statusSub.innerText    = 'Contacting exchange servers…';
    lightDot.style.background  = 'var(--neon-amber)';
    lightDot.style.boxShadow   = '0 0 10px var(--neon-amber)';
    lightDot.style.animation   = 'pulse 0.8s ease-in-out infinite';
    detailMsg.style.borderColor = 'rgba(255,193,7,0.35)';
    detailMsg.style.background  = 'rgba(255,193,7,0.05)';
    detailMsg.style.color       = 'var(--neon-amber)';
    detailMsg.style.display     = 'block';
    detailMsg.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Performing live connectivity check with Binance…';
  }

  try {
    const controller = new AbortController();
    const timeout    = setTimeout(() => controller.abort(), forceCheck ? 20000 : 6000);
    const endpoint   = forceCheck ? '/api/exchange-status/force' : '/api/exchange-status';
    const fetchOpts  = forceCheck
      ? { method: 'POST', signal: controller.signal }
      : { signal: controller.signal };

    const res = await fetch(endpoint, fetchOpts);
    clearTimeout(timeout);

    // Even a non-200 is okay — we always return JSON with diagnostic info
    const status = await res.json();

    // --- Populate telemetry fields ---
    accountName.innerText  = status.accountName || '—';
    exchangeName.innerText = status.exchange    || '—';
    latency.innerText      = (status.latency_ms !== null && status.latency_ms !== undefined)
      ? `${status.latency_ms} ms` : '—';
    stream.innerText       = status.streaming   ? 'ONLINE' : 'OFFLINE';
    // Show server-side lastChecked if available, else browser local time
    lastCheck.innerText    = status.lastChecked || new Date().toLocaleTimeString();

    // Stop pulse animation
    lightDot.style.animation = '';

    // --- Map status to UI state ---
    const s = status.status || 'UNKNOWN';

    if (s === 'CONNECTED') {
      statusTitle.innerText = 'CONNECTED';
      statusSub.innerText   = 'Exchange API reachable & credentials valid.';
      lightDot.style.background = 'var(--neon-emerald)';
      lightDot.style.boxShadow  = '0 0 14px var(--neon-emerald)';
      detailMsg.style.borderColor = 'rgba(0,230,118,0.35)';
      detailMsg.style.background  = 'rgba(0,230,118,0.04)';
      detailMsg.style.color       = 'var(--neon-emerald)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = `<i class="fa-solid fa-circle-check"></i> ${status.details || 'API validated successfully.'}`;

    } else if (s === 'SIMULATED') {
      statusTitle.innerText = 'SIMULATED';
      statusSub.innerText   = 'Paper trading engine active.';
      lightDot.style.background = 'var(--neon-cyan)';
      lightDot.style.boxShadow  = '0 0 14px var(--neon-cyan)';
      detailMsg.style.borderColor = 'rgba(0,184,212,0.35)';
      detailMsg.style.background  = 'rgba(0,184,212,0.04)';
      detailMsg.style.color       = 'var(--neon-cyan)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = '<i class="fa-solid fa-circle-info"></i> Running in safe Paper Trading mode. No real funds are at risk.';

    } else if (s === 'CHECKING') {
      statusTitle.innerText = 'CHECKING…';
      statusSub.innerText   = 'Background monitor is pinging exchange…';
      lightDot.style.background = 'var(--neon-amber)';
      lightDot.style.boxShadow  = '0 0 10px var(--neon-amber)';
      lightDot.style.animation  = 'pulse 1.2s ease-in-out infinite';
      detailMsg.style.borderColor = 'rgba(255,193,7,0.35)';
      detailMsg.style.background  = 'rgba(255,193,7,0.04)';
      detailMsg.style.color       = 'var(--neon-amber)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> First connection check in progress… this takes a few seconds.';

    } else if (s === 'API_KEY_ERROR') {
      statusTitle.innerText = 'API KEY ERROR';
      statusSub.innerText   = 'Credentials rejected by exchange.';
      lightDot.style.background = 'var(--neon-crimson)';
      lightDot.style.boxShadow  = '0 0 14px var(--neon-crimson)';
      lightDot.style.animation  = '';
      detailMsg.style.borderColor = 'rgba(239,83,80,0.4)';
      detailMsg.style.background  = 'rgba(239,83,80,0.06)';
      detailMsg.style.color       = 'var(--neon-crimson)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> <strong>API Key Rejected:</strong> ${status.details || 'Invalid API key or secret. Check your credentials in the Control Panel.'}`;

    } else if (s === 'NO_CREDENTIALS') {
      statusTitle.innerText = 'NO CREDENTIALS';
      statusSub.innerText   = 'API key and secret not set.';
      lightDot.style.background = 'var(--neon-crimson)';
      lightDot.style.boxShadow  = '0 0 14px var(--neon-crimson)';
      lightDot.style.animation  = '';
      detailMsg.style.borderColor = 'rgba(239,83,80,0.4)';
      detailMsg.style.background  = 'rgba(239,83,80,0.06)';
      detailMsg.style.color       = 'var(--neon-crimson)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = '<i class="fa-solid fa-key"></i> <strong>Missing credentials.</strong> Open the Control Panel → Create Account → select "Real Trading" and enter your API Key &amp; Secret.';

    } else if (s === 'NO_ACCOUNT') {
      statusTitle.innerText = 'NO ACCOUNT';
      statusSub.innerText   = 'No active account configured.';
      lightDot.style.background = 'var(--neon-amber)';
      lightDot.style.boxShadow  = '0 0 10px var(--neon-amber)';
      lightDot.style.animation  = '';
      detailMsg.style.borderColor = 'rgba(255,193,7,0.35)';
      detailMsg.style.background  = 'rgba(255,193,7,0.04)';
      detailMsg.style.color       = 'var(--neon-amber)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = '<i class="fa-solid fa-circle-exclamation"></i> No account found. Open the Control Panel and create a trading account profile first.';

    } else if (s === 'OFFLINE' || s === 'EXCHANGE_UNREACHABLE') {
      statusTitle.innerText = 'OFFLINE';
      statusSub.innerText   = 'Cannot reach exchange servers.';
      lightDot.style.background = 'var(--neon-crimson)';
      lightDot.style.boxShadow  = '0 0 14px var(--neon-crimson)';
      lightDot.style.animation  = '';
      detailMsg.style.borderColor = 'rgba(239,83,80,0.4)';
      detailMsg.style.background  = 'rgba(239,83,80,0.06)';
      detailMsg.style.color       = 'var(--neon-crimson)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = `<i class="fa-solid fa-wifi"></i> <strong>No Connection:</strong> ${status.details || 'Unable to reach Binance. Check your internet connection or firewall settings.'}`;

    } else {
      // Catch-all for API_ERROR, ERROR, UNKNOWN, etc.
      statusTitle.innerText = s.replace(/_/g, ' ');
      statusSub.innerText   = 'Exchange connectivity issue detected.';
      lightDot.style.background = 'var(--neon-amber)';
      lightDot.style.boxShadow  = '0 0 10px var(--neon-amber)';
      lightDot.style.animation  = '';
      detailMsg.style.borderColor = 'rgba(255,193,7,0.35)';
      detailMsg.style.background  = 'rgba(255,193,7,0.04)';
      detailMsg.style.color       = 'var(--neon-amber)';
      detailMsg.style.display     = 'block';
      detailMsg.innerHTML = `<i class="fa-solid fa-circle-exclamation"></i> <strong>Connectivity Issue:</strong> ${status.details || 'Unknown error. Check the System Logs panel for details.'}`;
    }

  } catch (e) {
    // Network failure — show it in the UI, not just console!
    console.error('[Exchange Monitor] Fetch error:', e);
    if (!statusTitle) return;

    lightDot.style.animation  = '';
    lightDot.style.background = 'var(--neon-crimson)';
    lightDot.style.boxShadow  = '0 0 14px var(--neon-crimson)';

    if (e.name === 'AbortError') {
      statusTitle.innerText = 'TIMEOUT';
      statusSub.innerText   = 'Exchange check timed out.';
      detailMsg.innerHTML   = '<i class="fa-solid fa-clock"></i> <strong>Request timed out.</strong> Exchange check took too long. Check your internet connection and try again.';
    } else {
      statusTitle.innerText = 'UNREACHABLE';
      statusSub.innerText   = 'Backend server not responding.';
      detailMsg.innerHTML   = `<i class="fa-solid fa-server"></i> <strong>Server Error:</strong> Cannot reach the bot backend. Is Python/Flask running? (${e.message})`;
    }

    detailMsg.style.borderColor = 'rgba(239,83,80,0.4)';
    detailMsg.style.background  = 'rgba(239,83,80,0.06)';
    detailMsg.style.color       = 'var(--neon-crimson)';
    detailMsg.style.display     = 'block';
    lastCheck.innerText = new Date().toLocaleTimeString();
  }
}

// Force re-check now button handler — hits /api/exchange-status/force which blocks until Binance responds
async function checkExchangeStatusNow() {
  const refreshBtn = document.getElementById('emRefreshBtn');
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.querySelector('i').className = 'fa-solid fa-rotate fa-spin';
  }
  await fetchExchangeStatus(true);
  if (refreshBtn) {
    refreshBtn.disabled = false;
    refreshBtn.querySelector('i').className = 'fa-solid fa-rotate';
  }
}

// Control Panel open/close handlers
function openControlPanel() {
  document.getElementById('controlPanel').classList.add('open');
  document.getElementById('cpOverlay').classList.add('open');
}

function closeControlPanel() {
  document.getElementById('controlPanel').classList.remove('open');
  document.getElementById('cpOverlay').classList.remove('open');
}

// Poll exchange status every 5 seconds
setInterval(fetchExchangeStatus, 5000);
// Initial immediate check
fetchExchangeStatus();

window.addEventListener('DOMContentLoaded', () => {
  // Sync sliders value display
  capitalSlider.addEventListener('input', (e) => {
    capitalSliderVal.innerText = `$${e.target.value}`;
  });
  maxTradesSlider.addEventListener('input', (e) => {
    maxTradesSliderVal.innerText = e.target.value;
  });

  // Toggle API credentials display on registration form
  accMode.addEventListener('change', (e) => {
    if (e.target.value === 'real') {
      credentialsWrapper.classList.remove('hidden');
      initialBalanceRow.classList.add('hidden');
    } else {
      credentialsWrapper.classList.add('hidden');
      initialBalanceRow.classList.remove('hidden');
    }
  });

  // Attach controls listeners
  addTokenBtn.addEventListener('click', handleAddToken);
  addTokenInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleAddToken(); });
  if (saveSettingsBtn) {
    saveSettingsBtn.addEventListener('click', handleSaveSettings);
  }
  createAccountForm.addEventListener('submit', handleCreateAccount);
  botStatusToggle.addEventListener('change', handleBotStatusChange);
  confirmAccountSwitchBtn.addEventListener('click', handleConfirmAccountSwitch);
  document.getElementById('closeAllPositionsBtn').addEventListener('click', handleCloseAllPositions);
  
  // Watchlist Selector Change Event
  watchlistSelect.addEventListener('change', handleWatchlistSelectChange);

  // Fetch initial state and start polling / streaming
  fetchState(true);
  
  // Poll state every 2 seconds for balance, trade logging, and live console updates
  setInterval(() => fetchState(false), 2000);

  // Live PnL updates every second in browser from WebSocket prices
  setInterval(updateLiveUnrealizedPnL, 1000);
});

// --- API COMMUNICATIONS ---
async function fetchState(isInitialLoad = false) {
  try {
    const res = await fetch('/api/state');
    if (!res.ok) throw new Error('API server unreachable');
    const state = await res.json();
    
    // Defensive check: If server responded with an empty state (e.g. while loading)
    if (!state || !state.activeAccountName || !state.accounts) {
      console.warn('Received uninitialized or empty state from backend.');
      return;
    }
    
    const activeAcc = state.accounts[state.activeAccountName];
    if (!activeAcc) return;

    // Check if active watchlist symbols changed to manage WebSockets
    const oldActiveWl = appState && appState.accounts && appState.accounts[appState.activeAccountName]
      ? appState.accounts[appState.activeAccountName].activeWatchlistName : '';
    
    const oldGlobalWls = (appState && appState.globalWatchlists) ? appState.globalWatchlists : {};
    const oldWatchlist = oldGlobalWls[oldActiveWl] || [];
    
    const newActiveWl = activeAcc.activeWatchlistName;
    const newGlobalWls = state.globalWatchlists || {};
    const newWatchlist = newGlobalWls[newActiveWl] || [];
    
    appState = state;
    
    renderDashboard(isInitialLoad);
    
    // Manage Binance price feed streams if watchlist or active watchlist name updated
    const listChanged = JSON.stringify(oldWatchlist) !== JSON.stringify(newWatchlist);
    const modeChanged = oldActiveWl !== newActiveWl;
    
    if (listChanged || modeChanged || isInitialLoad) {
      const watchlistAndPositions = [...new Set([...newWatchlist, ...Object.keys(activeAcc.positions)])];
      connectBinanceWebSocket(watchlistAndPositions);
    }
  } catch (err) {
    console.error('Failed to sync bot state:', err);
    // Detect network connectivity issues
    const msg = err.message && err.message.toLowerCase().includes('failed to fetch')
      ? 'No internet connection or backend unreachable!'
      : 'Failed to connect to trading backend!';
    showToast(msg, 'danger');
  }
}

// --- RENDER FUNCTIONS ---
function renderDashboard(isInitialLoad) {
  const activeAcc = appState.accounts[appState.activeAccountName];
  if (!activeAcc) return;

  // Render Trading Mode & Accounts Header
  const isReal = activeAcc.mode === 'real';
  modeBadge.className = `trading-mode-badge ${isReal ? 'real-mode' : 'paper-mode'}`;
  modeLabel.innerText = isReal ? 'LIVE TRADING MODE' : 'PAPER TRADING MODE';

  // Toggle Slider Switch and Status LED
  botStatusToggle.checked = appState.tradingActive;
  if (appState.tradingActive) {
    statusPulse.className = 'pulse-indicator active';
  } else {
    statusPulse.className = 'pulse-indicator';
  }

  // Show/Hide total balance input based on Paper/Real mode
  if (isReal) {
    totalBalanceGroup.classList.add('hidden');
    if (capitalSlider.closest('.cp-block')) {
      capitalSlider.closest('.cp-block').style.display = 'none';
    }
  } else {
    totalBalanceGroup.classList.remove('hidden');
    if (capitalSlider.closest('.cp-block')) {
      capitalSlider.closest('.cp-block').style.display = 'block';
    }
  }

  // Populate Accounts dropdown
  if (isInitialLoad) {
    activeAccountSelect.innerHTML = '';
    Object.keys(appState.accounts).forEach(name => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.innerText = `${name} (${appState.accounts[name].mode.toUpperCase()})`;
      if (name === appState.activeAccountName) opt.selected = true;
      activeAccountSelect.appendChild(opt);
    });
    
    // Set settings inputs
    capitalSlider.value = activeAcc.allocatedCapital;
    capitalSliderVal.innerText = `$${activeAcc.allocatedCapital}`;
    maxTradesSlider.value = activeAcc.maxConcurrentTrades;
    maxTradesSliderVal.innerText = activeAcc.maxConcurrentTrades;
    sheetsWebhookUrl.value = appState.googleSheetsWebhookUrl || '';
    
    if (!isReal) {
      totalBalanceInput.value = activeAcc.totalBalance;
    }
  }

  // Track select switch change
  activeAccountSelect.onchange = (e) => {
    pendingAccountToSwitch = e.target.value;
    openModal('accountSwitchModal');
  };

  // Populate Watchlist selector dropdown
  populateWatchlistSelect(activeAcc);

  // Render Core Top Metrics Cards
  const livePnL = getLiveUnrealizedPnLVal();
  
  if (isReal) {
    // Hide Safe Balance card
    if (metricSafeBalance.closest('.metric-card')) {
      metricSafeBalance.closest('.metric-card').style.display = 'none';
    }
    
    // Repurpose Allowed for Trading to IN-PLAY CAPITAL
    const allowedCard = metricAllocatedCapital.closest('.metric-card');
    if (allowedCard) {
      allowedCard.querySelector('.metric-title').innerText = 'IN-PLAY CAPITAL';
      allowedCard.querySelector('.metric-desc').innerText = 'Value of active open positions';
    }
    const inPlayVal = getActiveTradesValue();
    metricAllocatedCapital.innerText = `$${inPlayVal.toFixed(2)}`;
    
    // Total Balance = live account Net Asset Value from Binance
    const totalVal = activeAcc.totalBalance;
    metricTotalBalance.innerText = `$${totalVal.toFixed(2)}`;
    
    // Free Balance = activeAcc.balance
    metricFreeBalance.innerText = `$${activeAcc.balance.toFixed(2)}`;

    // Show Portfolio Holdings section (real mode only)
    const holdingsSection = document.getElementById('holdingsSection');
    if (holdingsSection) holdingsSection.style.display = 'block';
  } else {
    // Restore Standard Paper Trading Display
    if (metricSafeBalance.closest('.metric-card')) {
      metricSafeBalance.closest('.metric-card').style.display = 'block';
    }
    
    const allowedCard = metricAllocatedCapital.closest('.metric-card');
    if (allowedCard) {
      allowedCard.querySelector('.metric-title').innerText = 'ALLOWED FOR TRADING';
      allowedCard.querySelector('.metric-desc').innerText = 'Max capital assigned to bot scanner';
    }
    
    metricTotalBalance.innerText = `$${(activeAcc.totalBalance + livePnL).toFixed(2)}`;
    
    const safeVal = Math.max(0, activeAcc.totalBalance - activeAcc.allocatedCapital);
    metricSafeBalance.innerText = `$${safeVal.toFixed(2)}`;
    
    metricAllocatedCapital.innerText = `$${activeAcc.allocatedCapital.toFixed(2)}`;
    metricFreeBalance.innerText = `$${activeAcc.balance.toFixed(2)}`;

    // Hide Portfolio Holdings section (paper mode)
    const holdingsSection = document.getElementById('holdingsSection');
    if (holdingsSection) holdingsSection.style.display = 'none';
  }

  // Completed Trade Metrics
  const history = activeAcc.history || [];
  const journal = activeAcc.journal || { totalTrades: 0, winningTrades: 0, losingTrades: 0, totalPnL: 0 };
  
  const pnlClass = journal.totalPnL >= 0 ? 'text-success' : 'text-danger';
  metricRealizedPnL.className = `metric-val ${pnlClass}`;
  metricRealizedPnL.innerText = `${journal.totalPnL >= 0 ? '+' : ''}$${journal.totalPnL.toFixed(2)}`;
  metricRealizedDesc.innerText = `${journal.totalTrades} trades completed`;

  const totalTrades = journal.totalTrades;
  const wins = journal.winningTrades;
  const losses = journal.losingTrades;
  const winRatePct = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : '0.0';
  metricWinRate.innerText = `${winRatePct}%`;
  metricWinRatio.innerText = `${wins} W / ${losses} L`;

  // Render Active Watchlist (coins from GLOBAL pool)
  const globalWls = appState.globalWatchlists || {};
  const activeWl = globalWls[activeAcc.activeWatchlistName] || [];
  renderWatchlist(activeWl);

  // Render Open Positions
  renderPositions(activeAcc.positions);

  // Render Console Activity Logs
  renderTerminalLogs(appState.logs || []);

  // Render History logs
  renderHistory(history);

  // Render accounts list
  renderAccountsList();
  
  // Render Strategy Signals Table
  renderStrategyTable(activeWl);
}

function populateWatchlistSelect(activeAcc) {
  const selectNode = watchlistSelect;
  const currentSelection = activeAcc.activeWatchlistName;
  
  // Use GLOBAL watchlists pool — same list shown for all accounts
  const globalWls = appState.globalWatchlists || {};
  
  selectNode.innerHTML = '';
  Object.keys(globalWls).forEach(name => {
    const opt = document.createElement('option');
    opt.value = name;
    opt.innerText = name;
    if (name === currentSelection) opt.selected = true;
    selectNode.appendChild(opt);
  });
}

function getActiveTradesValue() {
  const activeAcc = appState.accounts[appState.activeAccountName];
  if (!activeAcc) return 0;
  
  let val = 0;
  Object.keys(activeAcc.positions).forEach(symbol => {
    const pos = activeAcc.positions[symbol];
    const price = (latestPrices[symbol] && latestPrices[symbol].price) ? latestPrices[symbol].price : pos.buyPrice;
    const size = pos.remainingSize !== undefined ? pos.remainingSize : pos.size;
    val += size * price;
  });
  return val;
}

function getLiveUnrealizedPnLVal() {
  const activeAcc = appState ? appState.accounts[appState.activeAccountName] : null;
  if (!activeAcc) return 0;
  let totalPnlUsd = 0;
  Object.keys(activeAcc.positions).forEach(symbol => {
    const pos = activeAcc.positions[symbol];
    const currPrice = latestPrices[symbol] ? latestPrices[symbol].price : null;
    if (currPrice) {
      const size = pos.remainingSize !== undefined ? pos.remainingSize : pos.size;
      totalPnlUsd += (currPrice - pos.buyPrice) * size;
    }
  });
  return totalPnlUsd;
}

function renderWatchlist(watchlist) {
  if (watchlist.length === 0) {
    watchlistList.innerHTML = '<div class="watchlist-empty">Watchlist empty. Add coins below!</div>';
    return;
  }

  watchlistList.innerHTML = '';
  watchlist.forEach(symbol => {
    const priceObj = latestPrices[symbol];
    const displayPrice = priceObj ? priceObj.price.toFixed(4) : 'Loading...';
    const pct = priceObj ? priceObj.pctChange : '0.00';
    
    let pctClass = 'text-muted';
    if (parseFloat(pct) > 0) pctClass = 'text-success';
    if (parseFloat(pct) < 0) pctClass = 'text-danger';

    const item = document.createElement('div');
    item.className = 'watchlist-item';
    item.innerHTML = `
      <div class="watchlist-coin-info">
        <span class="watchlist-symbol">${symbol}</span>
        <span class="watchlist-tag">SPOT/USDT</span>
      </div>
      <div class="watchlist-price-info">
        <span class="watchlist-price" id="wsPrice-${symbol}">${displayPrice}</span>
        <span class="${pctClass}" id="wsPct-${symbol}">${pct > 0 ? '+' : ''}${pct}%</span>
        <i class="fa-solid fa-trash watchlist-delete" onclick="handleRemoveToken('${symbol}')"></i>
      </div>
    `;
    watchlistList.appendChild(item);
  });
}

function renderPositions(positions) {
  const keys = Object.keys(positions);
  if (keys.length === 0) {
    positionsList.innerHTML = `
      <div class="positions-empty">
        <i class="fa-solid fa-ban"></i>
        <p>No active positions. The bot will scan on the 15-minute cycle.</p>
      </div>
    `;
    return;
  }

  positionsList.innerHTML = '';
  keys.forEach(symbol => {
    const pos = positions[symbol];
    const currentPrice = (latestPrices[symbol] && latestPrices[symbol].price) ? latestPrices[symbol].price : pos.buyPrice;
    const size = pos.remainingSize !== undefined ? pos.remainingSize : pos.size;
    const pnlUsd = (currentPrice - pos.buyPrice) * size;
    const pnlPct = ((currentPrice - pos.buyPrice) / pos.buyPrice) * 100;

    const card = document.createElement('div');
    card.className = 'position-card glass';
    card.id = `posCard-${symbol}`;
    
    // Set border glow color based on PnL
    if (pnlUsd >= 0) {
      card.style.borderLeftColor = 'var(--neon-emerald)';
    } else {
      card.style.borderLeftColor = 'var(--neon-crimson)';
    }

    card.innerHTML = `
      <div class="pos-coin-column">
        <span class="pos-symbol">${symbol} <span class="pos-strategy-tag">${pos.strategy}</span></span>
        <span class="pos-label">ENTRY TIME: ${pos.entryTime}</span>
      </div>
      <div class="pos-value-column">
        <span class="pos-label">SIZE / VALUE</span>
        <span class="pos-val">${size.toFixed(4)} ($${(size * currentPrice).toFixed(2)})</span>
      </div>
      <div class="pos-value-column">
        <span class="pos-label">ENTRY / CURR</span>
        <span class="pos-val">$${pos.buyPrice.toFixed(4)} / $${currentPrice.toFixed(4)}</span>
      </div>
      <div class="pos-value-column">
        <span class="pos-label">RISK SL / TP</span>
        <span class="pos-val text-danger">$${pos.stopLoss.toFixed(4)}</span>
        <span class="pos-val text-success">$${pos.takeProfit.toFixed(4)}</span>
      </div>
      <div class="pos-value-column align-right">
        <span class="pos-label">UNREALIZED P&L</span>
        <span class="pos-pnl-live ${pnlUsd >= 0 ? 'profit' : 'loss'}" id="pnlLive-${symbol}">
          ${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)} (${pnlPct.toFixed(2)}%)
        </span>
        <button class="btn btn-danger-outline btn-xs" style="margin-top: 4px;" onclick="handleClosePosition('${symbol}')">
          <i class="fa-solid fa-rectangle-xmark"></i> Close
        </button>
      </div>
    `;
    positionsList.appendChild(card);
  });
}

function renderTerminalLogs(logs) {
  // Save scroll status: check if the user was scrolled to the bottom
  const isScrolledToBottom = terminalLogs.scrollHeight - terminalLogs.clientHeight <= terminalLogs.scrollTop + 30;

  terminalLogs.innerHTML = '';
  if (logs.length === 0) {
    terminalLogs.innerHTML = '<div class="log-line text-muted">[00:00:00] Awaiting trade scheduler activity scan...</div>';
    return;
  }

  logs.forEach(log => {
    const div = document.createElement('div');
    div.className = 'log-line';
    
    // Classify log lines for dynamic coloring
    if (log.includes('Opened') || log.includes('BUY') || log.includes('Signal Triggered')) {
      div.className = 'log-line buy-log';
    } else if (log.includes('Closed') || log.includes('SELL') || log.includes('Liquidated')) {
      div.className = 'log-line sell-log';
    } else if (log.includes('SL hit') || log.includes('TP hit') || log.includes('Trigger') || log.includes('Error')) {
      div.className = 'log-line risk-log';
    } else if (log.includes('[Research]')) {
      div.className = 'log-line info';
    } else {
      div.className = 'log-line text-muted';
    }

    div.innerText = log;
    terminalLogs.appendChild(div);
  });

  // Auto-scroll log console
  if (isScrolledToBottom) {
    terminalLogs.scrollTop = terminalLogs.scrollHeight;
  }
}

function renderHistory(history) {
  if (history.length === 0) {
    historyTableBody.innerHTML = '<tr><td colspan="10" class="text-center text-muted">No trades recorded yet.</td></tr>';
    return;
  }

  historyTableBody.innerHTML = '';
  // Show newest trades first
  [...history].reverse().forEach(trade => {
    const tr = document.createElement('tr');
    
    const sideClass = trade.action === 'BUY' ? 'text-success' : 'text-danger';
    const isSell = trade.action === 'SELL';
    
    let pnlPctVal = 'N/A';
    let pnlUsdVal = 'N/A';
    if (isSell) {
      const pnlPct = trade.pnl_pct || 0;
      const pnlUsd = trade.pnl_usd || 0;
      const pnlClass = pnlUsd >= 0 ? 'text-success' : 'text-danger';
      pnlPctVal = `<span class="${pnlClass}">${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%</span>`;
      pnlUsdVal = `<span class="${pnlClass}">${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)}</span>`;
    }

    tr.innerHTML = `
      <td class="text-muted">${trade.timestamp}</td>
      <td class="font-bold">${trade.coin}</td>
      <td><span class="signal-badge ${trade.action === 'BUY' ? 'buy' : 'sell'}">${trade.action}</span></td>
      <td class="text-muted">${trade.strategy || 'MANUAL'}</td>
      <td>$${trade.price.toFixed(4)}</td>
      <td>${isSell ? '$' + trade.price.toFixed(4) : '-'}</td>
      <td>${trade.size.toFixed(5)}</td>
      <td>${pnlPctVal}</td>
      <td>${pnlUsdVal}</td>
      <td class="text-muted font-sm">${trade.reason || '-'}</td>
    `;
    historyTableBody.appendChild(tr);
  });
}

function renderAccountsList() {
  profilesList.innerHTML = '';
  Object.keys(appState.accounts).forEach(name => {
    const acc = appState.accounts[name];
    const isCurrent = name === appState.activeAccountName;
    const row = document.createElement('div');
    row.className = 'profile-row';
    
    row.innerHTML = `
      <div class="profile-row-info">
        <span class="profile-row-name">${name} ${isCurrent ? '<i class="fa-solid fa-circle-check text-success"></i>' : ''}</span>
        <span class="profile-row-badge ${acc.mode}">${acc.mode.toUpperCase()}</span>
      </div>
      ${isCurrent ? '' : `<i class="fa-solid fa-trash-can profile-row-delete" onclick="handleDeleteAccount('${name}')"></i>`}
    `;
    profilesList.appendChild(row);
  });
}

function renderStrategyTable(watchlist) {
  if (watchlist.length === 0) {
    strategyStatusBody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Awaiting tokens in watchlist...</td></tr>';
    return;
  }

  const signals = appState.strategySignals || {};

  strategyStatusBody.innerHTML = '';
  watchlist.forEach(symbol => {
    const coinSignals = signals[symbol] || {
      "RSI_BB_Reversion": "HOLD",
      "EMA_MACD_Crossover": "HOLD",
      "Stoch_EMA_Momentum": "HOLD"
    };

    const s1 = coinSignals["RSI_BB_Reversion"] || "HOLD";
    const s2 = coinSignals["EMA_MACD_Crossover"] || "HOLD";
    const s3 = coinSignals["Stoch_EMA_Momentum"] || "HOLD";

    const getBadge = (sig) => {
      const cls = sig.toLowerCase();
      return `<span class="signal-badge ${cls}">${sig}</span>`;
    };

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td class="font-bold">${symbol}</td>
      <td>${getBadge(s1)}</td>
      <td>${getBadge(s2)}</td>
      <td>${getBadge(s3)}</td>
    `;
    strategyStatusBody.appendChild(tr);
  });
}

// --- SUB-SECOND LIVE PRICING INTERFACES (WEBSOCKETS) ---
function connectBinanceWebSocket(watchlist) {
  if (binanceWs) {
    try {
      binanceWs.close();
    } catch(e){}
  }

  if (watchlist.length === 0) return;

  // Binance streams are lowercased
  const streams = watchlist.map(symbol => `${symbol.toLowerCase()}@ticker`).join('/');
  const wsUrl = `wss://stream.binance.com:9443/stream?streams=${streams}`;

  console.log(`[Binance WS] Connecting to streams: ${streams}`);
  
  binanceWs = new WebSocket(wsUrl);

  binanceWs.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const ticker = data.data;
      if (!ticker || !ticker.s) return;
      
      const symbol = ticker.s; // Symbol (e.g. BTCUSDT)
      const price = parseFloat(ticker.c); // Last price
      const pctChange = parseFloat(ticker.P); // 24h price change percentage

      // Store in-memory
      latestPrices[symbol] = {
        price,
        pctChange: pctChange.toFixed(2)
      };

      // Update prices inside Watchlist instantly
      const priceSpan = document.getElementById(`wsPrice-${symbol}`);
      const pctSpan = document.getElementById(`wsPct-${symbol}`);
      
      if (priceSpan) {
        const prevPrice = parseFloat(priceSpan.innerText) || 0;
        priceSpan.innerText = price.toFixed(price < 1 ? 5 : 2);
        
        // Flash dynamic color
        if (price > prevPrice) {
          priceSpan.className = 'watchlist-price price-up';
        } else if (price < prevPrice) {
          priceSpan.className = 'watchlist-price price-down';
        }
      }
      
      if (pctSpan) {
        pctSpan.innerText = `${pctChange >= 0 ? '+' : ''}${pctChange.toFixed(2)}%`;
        pctSpan.className = pctChange >= 0 ? 'text-success' : 'text-danger';
      }
    } catch (wsErr) {
      console.warn('[Binance WS] Parsing error:', wsErr);
    }
  };

  binanceWs.onclose = () => {
    console.log('[Binance WS] Stream connection closed.');
  };

  binanceWs.onerror = (err) => {
    console.error('[Binance WS] Error detected:', err);
  };
}

function updateLiveUnrealizedPnL() {
  const activeAcc = appState ? appState.accounts[appState.activeAccountName] : null;
  if (!activeAcc) return;

  let totalPnlUsd = 0;
  let totalCost = 0;
  const positions = activeAcc.positions;

  Object.keys(positions).forEach(symbol => {
    const pos = positions[symbol];
    const currPrice = latestPrices[symbol] ? latestPrices[symbol].price : null;
    
    if (currPrice) {
      const pnlUsd = (currPrice - pos.buyPrice) * pos.size;
      const pnlPct = ((currPrice - pos.buyPrice) / pos.buyPrice) * 100;
      totalPnlUsd += pnlUsd;
      totalCost += pos.allocatedCapital;

      // Update position cards live
      const liveSpan = document.getElementById(`pnlLive-${symbol}`);
      const posCard = document.getElementById(`posCard-${symbol}`);
      
      if (liveSpan) {
        liveSpan.innerText = `${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)} (${pnlPct.toFixed(2)}%)`;
        liveSpan.className = `pos-pnl-live ${pnlUsd >= 0 ? 'profit' : 'loss'}`;
      }
      
      if (posCard) {
        posCard.style.borderLeftColor = pnlUsd >= 0 ? 'var(--neon-emerald)' : 'var(--neon-crimson)';
      }
    } else {
      totalCost += pos.allocatedCapital;
    }
  });

  // Update Live Total Balance Card dynamically in real-time
  metricTotalBalance.innerText = `$${(activeAcc.totalBalance + totalPnlUsd).toFixed(2)}`;

  // Update Header Metric Card
  if (totalCost > 0) {
    const totalPnlPct = (totalPnlUsd / totalCost) * 100;
    metricUnrealizedPnL.innerText = `${totalPnlUsd >= 0 ? '+' : ''}$${totalPnlUsd.toFixed(2)} (${totalPnlPct.toFixed(2)}%)`;
    
    const card = document.getElementById('unrealizedCard');
    if (totalPnlUsd > 0) {
      card.className = 'metric-card glass card-glow-green';
      metricUnrealizedPnL.className = 'metric-val text-success';
    } else if (totalPnlUsd < 0) {
      card.className = 'metric-card glass card-glow-crimson';
      metricUnrealizedPnL.className = 'metric-val text-danger';
    } else {
      card.className = 'metric-card glass';
      metricUnrealizedPnL.className = 'metric-val';
    }
  } else {
    metricUnrealizedPnL.innerText = '$0.00 (0.00%)';
    const card = document.getElementById('unrealizedCard');
    card.className = 'metric-card glass';
    metricUnrealizedPnL.className = 'metric-val';
  }
}

// --- FORM & CONTROLLER HANDLERS ---
async function handleBotStatusChange(e) {
  const proposedStatus = e.target.checked;
  
  if (!proposedStatus) {
    // If stopping, open confirmation modal
    e.target.checked = true; // Keep visually checked until choice
    openModal('stopWarningModal');
  } else {
    // Start trading bot scans
    await setBotTrading(true, 'soft_stop');
  }
}

async function confirmBotStop(action) {
  closeModal('stopWarningModal');
  await setBotTrading(false, action);
}

async function setBotTrading(status, action) {
  try {
    const res = await fetch('/api/toggle-trading', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, action })
    });
    const state = await res.json();
    appState = state;
    renderDashboard(false);
    showToast(status ? 'Bot Scanning Active!' : 'Bot Scanning Stopped!', status ? 'success' : 'warning');
  } catch (err) {
    showToast('Failed to toggle trading runner.', 'danger');
  }
}

async function handleAddToken() {
  const val = addTokenInput.value.trim().toUpperCase();
  if (!val) return;
  
  try {
    const res = await fetch('/api/watchlist/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol: val })
    });
    
    if (!res.ok) throw new Error();
    const state = await res.json();
    appState = state;
    addTokenInput.value = '';
    renderDashboard(false);
    showToast(`${val} added to watchlist!`, 'success');
  } catch(e) {
    showToast('Failed to add token.', 'danger');
  }
}

function quickAddToken(symbol) {
  addTokenInput.value = symbol;
  handleAddToken();
}

async function handleRemoveToken(symbol) {
  try {
    const res = await fetch('/api/watchlist/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbol })
    });
    
    if (!res.ok) throw new Error();
    const state = await res.json();
    appState = state;
    renderDashboard(false);
    showToast(`${symbol} removed from watchlist!`, 'warning');
  } catch(e) {
    showToast('Failed to remove token.', 'danger');
  }
}

// --- WATCHLIST GROUP ACTIONS ---
async function handleWatchlistSelectChange(e) {
  const selectedWl = e.target.value;
  try {
    const res = await fetch('/api/watchlist/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: selectedWl })
    });
    if (!res.ok) throw new Error();
    const state = await res.json();
    appState = state;
    latestPrices = {}; // Reset cached prices
    renderDashboard(false);
    showToast(`Switched active watchlist to "${selectedWl}"!`, 'success');
  } catch (err) {
    showToast('Failed to switch watchlist.', 'danger');
  }
}

async function handleCreateWatchlist() {
  const name = prompt("Enter a name for the new Watchlist:");
  if (!name || !name.trim()) return;
  
  try {
    const res = await fetch('/api/watchlist/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Failed to create watchlist.', 'danger');
      return;
    }
    appState = data;
    renderDashboard(false);
    showToast(`Watchlist "${name}" created successfully!`, 'success');
  } catch (err) {
    showToast('Failed to create watchlist.', 'danger');
  }
}

async function handleDeleteWatchlist() {
  const activeAcc = appState.accounts[appState.activeAccountName];
  const currentWl = activeAcc.activeWatchlistName;
  const globalWls = appState.globalWatchlists || {};
  
  if (Object.keys(globalWls).length <= 1) {
    showToast('Cannot delete the last remaining watchlist.', 'danger');
    return;
  }
  
  if (confirm(`Delete watchlist "${currentWl}" from the global pool? All accounts using it will be switched to the next available list.`)) {
    try {
      const res = await fetch('/api/watchlist/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: currentWl })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Failed to delete watchlist.', 'danger');
        return;
      }
      appState = data;
      renderDashboard(false);
      showToast(`Watchlist "${currentWl}" deleted from global pool.`, 'warning');
    } catch (err) {
      showToast('Failed to delete watchlist.', 'danger');
    }
  }
}

async function handleRenameWatchlist() {
  const activeAcc = appState.accounts[appState.activeAccountName];
  const currentWl = activeAcc.activeWatchlistName;
  
  const newName = prompt(`Rename watchlist "${currentWl}" to:`, currentWl);
  if (!newName || !newName.trim() || newName.trim() === currentWl) return;
  
  try {
    const res = await fetch('/api/watchlist/rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ oldName: currentWl, newName: newName.trim() })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Failed to rename watchlist.', 'danger');
      return;
    }
    appState = data;
    renderDashboard(false);
    showToast(`Watchlist renamed to "${newName.trim()}"!`, 'success');
  } catch (err) {
    showToast('Failed to rename watchlist.', 'danger');
  }
}

async function handleSaveSettings() {
  const cap = parseFloat(capitalSlider.value);
  const maxT = parseInt(maxTradesSlider.value);
  const url = sheetsWebhookUrl.value.trim();
  const totalB = totalBalanceInput && totalBalanceInput.value ? parseFloat(totalBalanceInput.value) : null;

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        maxTrades: maxT, 
        allocatedCapital: cap, 
        googleSheetsWebhookUrl: url,
        totalBalance: totalB
      })
    });
    
    if (!res.ok) throw new Error();
    const state = await res.json();
    appState = state;
    renderDashboard(false);
    showToast('Settings saved successfully!', 'success');
  } catch(e) {
    showToast('Failed to save settings.', 'danger');
  }
}

async function handleCreateAccount(e) {
  e.preventDefault();
  const name = accName.value.trim();
  const mode = accMode.value;
  const key = accApiKey.value.trim();
  const secret = accApiSecret.value.trim();
  const initB = mode === 'paper' ? (parseFloat(accInitialBalance.value) || 1000.0) : 0.0;

  try {
    const res = await fetch('/api/accounts/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ 
        name, 
        mode, 
        apiKey: key, 
        apiSecret: secret,
        initialBalance: initB
      })
    });
    
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Failed to create profile.', 'danger');
      return;
    }
    
    appState = data;
    accName.value = '';
    accApiKey.value = '';
    accApiSecret.value = '';
    accInitialBalance.value = '1000';
    renderDashboard(true); // Re-render selectors
    showToast(`Account Profile "${name}" created!`, 'success');
  } catch(e) {
    showToast('Failed to create account.', 'danger');
  }
}

async function handleDeleteAccount(name) {
  if (confirm(`Are you sure you want to delete profile "${name}"?`)) {
    try {
      const res = await fetch('/api/accounts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Failed to delete.', 'danger');
        return;
      }
      appState = data;
      renderDashboard(true);
      showToast('Profile deleted successfully.', 'warning');
    } catch(e) {
      showToast('Failed to delete profile.', 'danger');
    }
  }
}

async function handleConfirmAccountSwitch() {
  if (!pendingAccountToSwitch) return;
  closeModal('accountSwitchModal');
  
  try {
    const res = await fetch('/api/accounts/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: pendingAccountToSwitch })
    });
    
    if (!res.ok) throw new Error();
    const data = await res.json();
    appState = data;
    latestPrices = {}; // Reset cache
    renderDashboard(true);
    showToast(`Switched active profile to ${pendingAccountToSwitch}!`, 'success');
  } catch(e) {
    showToast('Failed to switch accounts.', 'danger');
  } finally {
    pendingAccountToSwitch = null;
  }
}

async function handleClosePosition(symbol) {
  if (confirm(`Do you want to manually market-close/liquidate ${symbol} instantly?`)) {
    try {
      const res = await fetch('/api/positions/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol })
      });
      const data = await res.json();
      if (!res.ok) {
        showToast(data.error || 'Close order failed.', 'danger');
        return;
      }
      appState = data;
      renderDashboard(false);
      showToast(`Liquidated ${symbol} successfully!`, 'warning');
    } catch(e) {
      showToast('Error liquidating position.', 'danger');
    }
  }
}

async function handleCloseAllPositions() {
  if (confirm('🚨 DANGER: Do you want to market liquidate ALL active open trades immediately?')) {
    try {
      const res = await fetch('/api/positions/close-all', {
        method: 'POST'
      });
      const data = await res.json();
      appState = data;
      renderDashboard(false);
      showToast('ALL POSITIONS LIQUIDATED!', 'danger');
    } catch(e) {
      showToast('Failed to liquidate positions.', 'danger');
    }
  }
}

// ── PORTFOLIO HOLDINGS ─────────────────────────────────────────
// Loads and renders all Binance asset holdings for real accounts.
let holdingsLoading = false;

async function loadHoldings() {
  if (holdingsLoading) return;
  holdingsLoading = true;
  const tbody = document.getElementById('holdingsTableBody');
  const refreshBtn = document.getElementById('refreshHoldingsBtn');
  if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Fetching from Binance...</td></tr>';
  if (refreshBtn) refreshBtn.disabled = true;

  try {
    const res = await fetch('/api/holdings');
    const data = await res.json();
    renderHoldings(data);
  } catch (err) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">Error: ${err.message}</td></tr>`;
  } finally {
    holdingsLoading = false;
    if (refreshBtn) refreshBtn.disabled = false;
  }
}

function renderHoldings(data) {
  const tbody = document.getElementById('holdingsTableBody');
  const totalLabel = document.getElementById('holdingsTotalLabel');
  if (!tbody) return;

  if (data.error) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center text-danger">${data.error}</td></tr>`;
    return;
  }

  const holdings = data.holdings || [];
  if (holdings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No holdings found.</td></tr>';
    return;
  }

  if (totalLabel) totalLabel.innerText = `Total: $${(data.totalUsd || 0).toFixed(2)}`;

  tbody.innerHTML = holdings.map((h, i) => {
    const isUsdt = h.isUsdt;
    const priceStr = isUsdt ? '$1.00' : (h.price > 0 ? `$${h.price < 0.01 ? h.price.toFixed(6) : h.price.toFixed(4)}` : '—');
    const valueStr = `$${h.usdValue.toFixed(2)}`;
    const valueCls = h.usdValue < 5 ? 'text-muted' : (h.usdValue >= 10 ? 'text-success' : '');
    const dustBadge = (!isUsdt && h.usdValue < 5) ? '<span style="font-size:0.68rem;background:rgba(255,200,0,0.15);color:#f5c542;padding:1px 5px;border-radius:4px;margin-left:4px;">dust</span>' : '';

    const sellSelectorInput = isUsdt ? '—' : `
      <div style="display:flex;gap:4px;align-items:center;">
        <select id="sellMode_${i}" class="cp-select" onchange="toggleSellInputMode(${i}, ${h.usdValue})" style="padding:3px 4px;font-size:0.78rem;min-width:60px;height:28px;">
          <option value="pct">%</option>
          <option value="usd">USD ($)</option>
        </select>
        <input type="number" id="sellVal_${i}" class="cp-input" value="100" min="1" max="100" step="any" style="padding:3px 6px;font-size:0.78rem;width:65px;height:28px;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);color:#fff;text-align:center;border-radius:4px;">
      </div>`;

    const actionCell = isUsdt ? '<span class="text-muted" style="font-size:0.78rem;">Base currency</span>' : `
      <button class="btn btn-danger btn-xs" onclick="sellHolding('${h.asset}', ${i})" ${h.usdValue < 1 ? 'disabled title="Value too small"' : ''}>
        <i class="fa-solid fa-arrow-right-from-bracket"></i> Sell
      </button>`;

    return `<tr>
      <td><strong>${h.asset}</strong>${dustBadge}</td>
      <td style="font-family:monospace;">${h.free.toFixed(h.free < 0.0001 ? 8 : 4)}</td>
      <td style="font-family:monospace;color:${h.locked > 0 ? '#f5a623' : 'inherit'}">${h.locked > 0 ? h.locked.toFixed(6) + ' 🔒' : '—'}</td>
      <td style="font-family:monospace;">${h.total.toFixed(h.total < 0.0001 ? 8 : 4)}</td>
      <td>${priceStr}</td>
      <td class="${valueCls}"><strong>${valueStr}</strong></td>
      <td>${sellSelectorInput}</td>
      <td>${actionCell}</td>
    </tr>`;
  }).join('');
}

function toggleSellInputMode(idx, maxUsd) {
  const modeSelect = document.getElementById(`sellMode_${idx}`);
  const valInput = document.getElementById(`sellVal_${idx}`);
  if (!modeSelect || !valInput) return;
  
  if (modeSelect.value === 'pct') {
    valInput.min = "1";
    valInput.max = "100";
    valInput.value = "100";
  } else {
    valInput.min = "1";
    valInput.max = maxUsd.toFixed(2);
    valInput.value = maxUsd.toFixed(2);
  }
}

async function sellHolding(asset, rowIdx) {
  const modeSelect = document.getElementById(`sellMode_${rowIdx}`);
  const valInput = document.getElementById(`sellVal_${rowIdx}`);
  if (!modeSelect || !valInput) return;
  
  const mode = modeSelect.value;
  const value = parseFloat(valInput.value);
  
  if (isNaN(value) || value <= 0) {
    showToast("Please enter a valid amount.", "danger");
    return;
  }
  
  let confirmMsg = "";
  if (mode === 'pct') {
    confirmMsg = `Sell ${value}% of ${asset} at market price? This is a LIVE order on Binance!`;
  } else {
    confirmMsg = `Sell $${value} worth of ${asset} at market price? This is a LIVE order on Binance!`;
  }
  
  if (!confirm(confirmMsg)) return;
  
  showToast(`Placing sell order for ${asset}...`, 'warning');
  
  try {
    const res = await fetch('/api/holdings/sell', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset, mode, value })
    });
    const data = await res.json();
    
    if (data.success) {
      showToast(`✅ ${data.message}`, 'success');
      setTimeout(() => loadHoldings(), 1500);
    } else {
      showToast(`❌ ${data.error}`, 'danger');
    }
  } catch (err) {
    showToast(`❌ Network error: ${err.message}`, 'danger');
  }
}

// Auto-load holdings when page first loads (if real account)
window.addEventListener('load', () => {
  setTimeout(() => {
    const section = document.getElementById('holdingsSection');
    if (section && section.style.display !== 'none') {
      loadHoldings();
    }
  }, 3000);
});

// --- VISUAL UTILITIES ---
function openModal(id) {
  document.getElementById(id).classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

function showToast(message, type = 'success') {
  toastMsg.innerText = message;
  toastNotification.className = `toast open ${type}`;
  
  let icon = 'fa-circle-info';
  if (type === 'success') icon = 'fa-circle-check';
  if (type === 'warning') icon = 'fa-circle-exclamation';
  if (type === 'danger') icon = 'fa-triangle-exclamation';
  toastIcon.className = `fa-solid ${icon}`;

  setTimeout(() => {
    toastNotification.classList.remove('open');
  }, 4000);
}
