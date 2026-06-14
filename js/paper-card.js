/**
 * 论文卡片渲染 + 论文属性辅助函数
 */

import { state } from './state.js';
import { escapeHTML, escapeAttribute, safeURL, formatDate, tagClass, parseDate, isCompleteDate } from './utils.js';

export function isPreprint(paper) {
    return paper.is_preprint === true || paper.publication_type === 'preprint' || (!paper.venue && !paper.conference);
}

export function hasPDF(paper) {
    return Boolean(paper.pdf_url || paper.preprint_pdf_url || paper.arxiv_id);
}

export function sourceLabel(source, paper = {}) {
    if (source === 'semantic_scholar') return 'Semantic Scholar';
    if (source === 'arxiv') return 'arXiv';
    if (source === 'google_scholar') {
        return String(paper.paper_url || '').includes('nature.com') ? 'Nature' : 'Google Scholar';
    }
    if (String(paper.paper_url || '').includes('nature.com')) return 'Nature';
    if (paper.semantic_scholar_id || String(paper.paper_url || '').includes('semanticscholar.org')) return 'Semantic Scholar';
    if (paper.arxiv_id || String(paper.arxiv_url || paper.paper_url || '').includes('arxiv.org')) return 'arXiv';
    return source ? String(source) : 'Literature';
}

export function publicationTypeLabel(type, preprint) {
    if (preprint) return 'Preprint';
    if (type === 'journal') return 'Journal';
    if (type === 'conference') return 'Conference';
    return 'Published';
}

export function sourceScore(paper) {
    const source = paper.source || '';
    if (source === 'semantic_scholar') return 10;
    if (source === 'arxiv') return 8;
    if (source === 'google_scholar' && paper.abstract_status === 'enriched') return 7;
    if (source === 'google_scholar') return 4;
    return 5;
}

export function daysSincePublished(paper) {
    if (!isCompleteDate(paper.published)) return 365;
    const date = parseDate(paper.published);
    if (Number.isNaN(date.getTime())) return 365;
    return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
}

export function tagScore(paper) {
    const tags = paper.tags || [];
    let score = 0;
    if (tags.includes('流体力学 / 智能CFD')) score += 8;
    if (tags.includes('机器学习')) score += 3;
    if (tags.some(tag => tag.includes('流动控制与强化学习'))) score += 3;
    return score;
}

export function recommendationDetails(paper) {
    const citation = Number(paper.citation_count || 0);
    const citationScore = citation > 0 ? Math.min(14, Math.log10(citation + 1) * 6) : 0;
    const recencyScore = Math.max(0, 12 - Math.min(daysSincePublished(paper), 180) / 15);
    const publishedScore = isPreprint(paper) ? 2 : 8;
    const pdfScore = hasPDF(paper) ? 6 : 0;
    const abstractScore = paper.abstract && paper.abstract_status !== 'unreliable_google_scholar_snippet' ? 5 : 0;
    const keywordScore = Array.isArray(paper.keywords) && paper.keywords.length > 0 ? 3 : 0;
    const score = sourceScore(paper) + citationScore + recencyScore + publishedScore + pdfScore + abstractScore + keywordScore + tagScore(paper);
    const reasons = [];
    if (!isPreprint(paper)) reasons.push('已发表');
    if (hasPDF(paper)) reasons.push('有PDF');
    if (paper.abstract && paper.abstract_status !== 'unreliable_google_scholar_snippet') reasons.push('摘要可靠');
    if ((paper.tags || []).includes('流体力学 / 智能CFD')) reasons.push('智能CFD');
    if (citation > 0) reasons.push(`引用${citation}`);
    if (citation === 0 && !paper.impact_factor) reasons.push('数据不足按日期补偿');
    return { score, reasons };
}

export function recommendationScore(paper) {
    return recommendationDetails(paper).score;
}

export function influenceScore(paper) {
    // 影响因子分（对数压缩，IF=100 得约 45 分）
    const if_val = Number(paper.impact_factor || 0);
    const ifScore = if_val > 0 ? Math.min(45, Math.log10(if_val + 1) * 22) : 0;
    // 引用影响分（对数压缩，引用=10000 得约 35 分）
    const citation = Number(paper.citation_count || 0);
    const citationScore = citation > 0 ? Math.min(35, Math.log10(citation + 1) * 14) : 0;
    // 正式发表加分
    const publishedScore = isPreprint(paper) ? 2 : 10;
    // 来源可信加分
    const source = paper.source || '';
    const sourceScore = (source === 'semantic_scholar' || source === 'openalex' || source === 'crossref') ? 5 : (source === 'google_scholar' ? 2 : 0);
    return ifScore + citationScore + publishedScore + sourceScore;
}

export function sortTimestamp(paper) {
    const parsed = parseDate(paper.published);
    const value = parsed.getTime();
    return Number.isNaN(value) ? 0 : value;
}

export function getPaperPDFUrl(paper) {
    if (paper.pdf_url) return safeURL(paper.pdf_url, '');
    if (paper.preprint_pdf_url) return safeURL(paper.preprint_pdf_url, '');
    if (paper.arxiv_id) return safeURL(`https://arxiv.org/pdf/${paper.arxiv_id}`, '');
    return '';
}

export function getVenueBadge(conference) {
    if (!conference) return null;
    const conferenceUpper = conference.toUpperCase();
    let badgeClass = 'badge-published';
    if (conferenceUpper.includes('NEURIPS')) badgeClass = 'badge-neurips';
    else if (conferenceUpper.includes('ICLR')) badgeClass = 'badge-iclr';
    else if (conferenceUpper.includes('ICML')) badgeClass = 'badge-icml';
    else if (conferenceUpper.includes('CVPR')) badgeClass = 'badge-cvpr';
    else if (conferenceUpper.includes('ICCV')) badgeClass = 'badge-iccv';
    else if (conferenceUpper.includes('ECCV')) badgeClass = 'badge-eccv';
    else if (conferenceUpper.includes('ACL')) badgeClass = 'badge-acl';
    else if (conferenceUpper.includes('EMNLP')) badgeClass = 'badge-emnlp';
    else if (conferenceUpper.includes('NAACL')) badgeClass = 'badge-naacl';
    else if (conferenceUpper.includes('AAAI')) badgeClass = 'badge-aaai';
    else if (conferenceUpper.includes('IJCAI')) badgeClass = 'badge-ijcai';
    return { class: badgeClass, text: conference };
}

/**
 * 分类路径标签（取最后一段）
 */
function categoryLabel(category) {
    if (category === 'all') return '全部';
    const parts = category.split('/').map(p => p.trim()).filter(Boolean);
    return parts[parts.length - 1] || category;
}

export function createPaperHTML(paper) {
    const paperId = String(paper.id || '');
    const escapedId = escapeAttribute(paperId);
    const title = escapeHTML(paper.title);
    const authors = escapeHTML(paper.authors);
    const hasReliableAbstract = Boolean(String(paper.abstract || '').trim())
        && paper.abstract_status !== 'unreliable_google_scholar_snippet';
    const abstract = hasReliableAbstract
        ? escapeHTML(paper.abstract)
        : '暂无可靠摘要。Google Scholar 仅提供搜索片段，已隐藏原始片段以避免误读。';
    const abstractSummary = hasReliableAbstract ? '查看摘要' : '摘要待补全';
    const published = escapeHTML(paper.published);
    const publishedFormatted = formatDate(paper.published);
    const dateFlag = (paper.date_status === 'year_only' || paper.date_status === 'unreliable')
        ? '<span class="date-flag" title="日期待核实">⚠</span>' : '';
    const earlyAccessBadge = paper.is_early_access
        ? '<span class="early-access-badge" title="预出版 / Ahead of Print">预出版</span>' : '';
    const tags = paper.tags ? paper.tags.map(tag => `<span class="tag ${tagClass(tag)}">${escapeHTML(categoryLabel(tag))}</span>`).join('') : '';
    const keywords = paper.keywords ? paper.keywords.map(kw => `<span class="tag keyword">${escapeHTML(kw)}</span>`).join('') : '';
    const checked = state.selectedPaperIds.has(paperId) ? 'checked' : '';
    const paperURL = safeURL(paper.paper_url || paper.arxiv_url, paperId ? `https://arxiv.org/abs/${encodeURIComponent(paperId)}` : '#');
    const keywordsSection = keywords ? `<div class="paper-keywords"><span class="keyword-label">关键词：</span>${keywords}</div>` : '';
    const preprint = isPreprint(paper);
    const status = preprint ? 'preprint' : 'published';
    const venue = paper.venue || paper.conference || '';
    const publicationType = publicationTypeLabel(paper.publication_type, preprint);
    const sourceBadge = `<span class="meta-item">${escapeHTML(sourceLabel(paper.source, paper))}</span>`;
    const typeBadge = `<span class="meta-item">${escapeHTML(publicationType)}</span>`;
    const doiLink = paper.doi ? `<a href="${escapeAttribute(safeURL(`https://doi.org/${paper.doi}`))}" target="_blank" rel="noopener noreferrer" class="code-link">DOI</a>` : '';
    const sourcePageLink = paper.paper_url ? `<a href="${escapeAttribute(safeURL(paper.paper_url))}" target="_blank" rel="noopener noreferrer" class="code-link">${escapeHTML(sourceLabel(paper.source, paper))}</a>` : '';
    const arxivLink = paper.arxiv_url ? `<a href="${escapeAttribute(safeURL(paper.arxiv_url))}" target="_blank" rel="noopener noreferrer" class="code-link">arXiv</a>` : '';
    const pdfLink = paper.pdf_url ? `<a href="${escapeAttribute(safeURL(paper.pdf_url))}" target="_blank" rel="noopener noreferrer" class="code-link">PDF</a>` : '';
    const preprintPdfLink = paper.preprint_pdf_url ? `<a href="${escapeAttribute(safeURL(paper.preprint_pdf_url))}" target="_blank" rel="noopener noreferrer" class="code-link">Preprint PDF</a>` : '';
    let codeLink = '';
    if (paper.code_link) {
        codeLink = `<a href="${escapeAttribute(safeURL(paper.code_link))}" target="_blank" rel="noopener noreferrer" class="code-link">Code/Project</a>`;
    }
    let venueBadge = '';
    if (venue) {
        const badgeInfo = getVenueBadge(venue);
        if (badgeInfo) {
            venueBadge = `<span class="venue-badge ${badgeInfo.class}">${escapeHTML(badgeInfo.text)}</span>`;
        }
    }
    const safeCitationText = paper.citation_count ? `引用数: ${escapeHTML(paper.citation_count)}` : '';
    const recommendation = recommendationDetails(paper);
    const safeScoreText = recommendation.score.toFixed(1);
    const scoreReasons = recommendation.reasons.length ? recommendation.reasons.join(' · ') : '数据不足时按日期补偿';

    return `
    <article class="paper-card" data-date="${published}" data-status="${status}" data-tags="${paper.tags ? escapeAttribute(paper.tags.join(',')) : ''}" data-paper-id="${escapedId}">
        <div class="paper-select">
            <input type="checkbox" class="paper-checkbox" id="check-${escapedId}" data-paper-id="${escapedId}" ${checked}>
            <label for="check-${escapedId}"></label>
        </div>
        <div class="paper-content">
            <h2 class="paper-title">
                <a href="${escapeAttribute(paperURL)}" target="_blank" rel="noopener noreferrer">${title}</a>
            </h2>
            <div class="paper-meta">
                ${paper.is_early_access
                    ? `${earlyAccessBadge}<span class="early-access-date">暂未出版</span>`
                    : `<span class="meta-item" title="${published}">${publishedFormatted}</span>${dateFlag}`
                }
                ${sourceBadge}
                ${typeBadge}
                ${venueBadge}
                ${safeCitationText ? `<span class="meta-item">${safeCitationText}</span>` : ''}
                <span class="score-pill" title="${escapeAttribute(scoreReasons)}">推荐分 ${safeScoreText}</span>
                ${sourcePageLink}
                ${doiLink}
                ${arxivLink}
                ${pdfLink}
                ${preprintPdfLink}
                ${codeLink}
            </div>
            <div class="paper-authors">
                ${authors}
            </div>
            <div class="paper-tags">
                ${tags}
            </div>
            ${keywordsSection}
            <div class="paper-abstract">
                <details>
                    <summary>${abstractSummary}</summary>
                    <p>${abstract}</p>
                </details>
            </div>
        </div>
    </article>
`;
}
