const TRANSLATIONS = {
  zh: {
    header_subtitle: '局域网',
    net_checking: '检测中', net_ok: '正常', net_warn: '无外网', net_bad: '断连',
    net_banner_lan_down: '无法连接到 Mac，请检查局域网连接',
    net_banner_inet_warn: 'Mac 当前无互联网连接，Claude 可能无法运行',
    section_pinned: '📌 置顶',
    section_other: '其他项目',
    section_all: '全部项目',
    guide_title: '使用方式',
    guide_step1: '点击项目启动 Claude 会话',
    guide_step2: '打开 Claude App → 底部 Code 标签',
    guide_step3: '找到同名会话（绿点）点击连接',
    btn_stop: '停止',
    empty_loading: '加载中...',
    modal_running_desc: '该项目已有运行中的 Claude 会话，你想怎么处理？',
    btn_reuse: '继续使用现有会话',
    btn_new_session: '终止并新建会话',
    btn_cancel: '取消',
    toast_reuse: '前往 Claude App → Code 标签连接',
    toast_stopped: '已停止',
    toast_started: '已启动 → Claude App → Code 标签',
    toast_net_offline: '网络已断开',
    toast_net_restored: '网络已恢复',
    settings_title: '设置',
    settings_appearance: '外观',
    settings_language: '语言',
    settings_theme: '主题',
    theme_light: '浅色', theme_dark: '深色', theme_auto: '跟随系统',
    btn_close: '关闭',
    btn_pin: '收藏',
    btn_hide: '隐藏',
    btn_unfavorite: '取消收藏',
    btn_favorite: '收藏',
    tab_favorites: '⭐ 收藏',
    tab_all: '🌐 全部',
    search_placeholder: '搜索项目路径...',
    section_recent: '最近 7 天',
    section_older: '更早',
    search_results: '搜索结果',
    sessions_label: '次历史会话',
    sess_live: '● 运行中',
    sess_view: '查看记录 ›',
    sess_new_title: '＋ 新建会话',
    sess_new_hint: '在此目录创建新对话',
    sess_name_label: '会话名：',
    msg_resume: '恢复会话',
    msg_back: '‹ 会话列表',
    msg_empty: '暂无消息记录',
    toast_resumed: '会话已恢复',
    toast_path_missing: '目录不存在，无法启动',
  },
  en: {
    header_subtitle: 'LAN',
    net_checking: 'Checking', net_ok: 'OK', net_warn: 'No WAN', net_bad: 'Offline',
    net_banner_lan_down: 'Cannot reach Mac — check LAN connection',
    net_banner_inet_warn: 'Mac has no internet — Claude may not work',
    section_pinned: '📌 Pinned',
    section_other: 'Other Projects',
    section_all: 'All Projects',
    guide_title: 'How to use',
    guide_step1: 'Tap a project to start a Claude session',
    guide_step2: 'Open Claude App → Code tab at the bottom',
    guide_step3: 'Find the session (green dot) and connect',
    btn_stop: 'Stop',
    empty_loading: 'Loading...',
    modal_running_desc: 'This project has a running Claude session.',
    btn_reuse: 'Use existing session',
    btn_new_session: 'Kill and restart',
    btn_cancel: 'Cancel',
    toast_reuse: 'Go to Claude App → Code tab',
    toast_stopped: 'Stopped',
    toast_started: 'Started → Claude App → Code tab',
    toast_net_offline: 'Network offline',
    toast_net_restored: 'Network restored',
    settings_title: 'Settings',
    settings_appearance: 'Appearance',
    settings_language: 'Language',
    settings_theme: 'Theme',
    theme_light: 'Light', theme_dark: 'Dark', theme_auto: 'Auto',
    btn_close: 'Close',
    btn_pin: 'Favorite',
    btn_hide: 'Hide',
    btn_unfavorite: 'Unfavorite',
    btn_favorite: 'Favorite',
    tab_favorites: '⭐ Favorites',
    tab_all: '🌐 All',
    search_placeholder: 'Search project paths...',
    section_recent: 'Last 7 days',
    section_older: 'Older',
    search_results: 'Results',
    sessions_label: 'sessions',
    sess_live: '● Running',
    sess_view: 'View ›',
    sess_new_title: '＋ New Session',
    sess_new_hint: 'Create a new conversation in this directory',
    sess_name_label: 'Session name: ',
    msg_resume: 'Resume',
    msg_back: '‹ Sessions',
    msg_empty: 'No messages found',
    toast_resumed: 'Session resumed',
    toast_path_missing: 'Directory not found',
  },
};

// eslint-disable-next-line no-unused-vars
let _lang = localStorage.getItem('launcher_lang') || 'zh';

// eslint-disable-next-line no-unused-vars
function t(key) {
  return (TRANSLATIONS[_lang] || TRANSLATIONS.zh)[key] || key;
}

// eslint-disable-next-line no-unused-vars
function setLang(lang) {
  _lang = lang;
  localStorage.setItem('launcher_lang', lang);
  applyLang();
}

function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });
  if (typeof render === 'function') render();
  if (typeof renderSheet === 'function') renderSheet();
}

document.addEventListener('DOMContentLoaded', applyLang);
