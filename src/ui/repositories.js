// Repository Management JavaScript

let repositories = [];
let repositoryStats = null;

const PRIORITY_CONFIG = {
    1: { label: 'High', className: 'priority-high', badgeClass: 'bg-danger' },
    2: { label: 'Medium', className: 'priority-medium', badgeClass: 'bg-warning text-dark' },
    3: { label: 'Low', className: 'priority-low', badgeClass: 'bg-success' }
};

const LANGUAGE_BADGE_CLASS = {
    DotNet: 'bg-primary',
    'Node.js': 'bg-success',
    'Web/Browser': 'bg-info text-dark',
    JavaScript: 'bg-warning text-dark',
    Python: 'bg-secondary',
    Java: 'bg-danger',
    Other: 'bg-dark'
};

document.addEventListener('DOMContentLoaded', () => {
    const repoUrlInput = document.getElementById('repoUrl');
    if (repoUrlInput) {
        repoUrlInput.addEventListener('blur', () => handleRepoUrlChange(repoUrlInput.value));
    }
    loadRepositories();
});

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value == null ? '' : String(value);
    return div.innerHTML;
}

function parseRepositoryInput(rawValue) {
    if (!rawValue) {
        return null;
    }

    let value = rawValue.trim();
    if (!value) {
        return null;
    }

    value = value.replace(/^git@github\.com:/i, 'https://github.com/');
    value = value.replace(/\.git$/i, '');

    if (/^[^\s/]+\/[\w.-]+$/i.test(value)) {
        const [ownerRaw, nameRaw] = value.split('/');
        const owner = ownerRaw.trim();
        const name = nameRaw.trim();
        if (!owner || !name) {
            return null;
        }
        return { owner, name };
    }

    if (value.toLowerCase().startsWith('github.com/')) {
        value = `https://${value}`;
    }

    try {
        if (!/^https?:\/\//i.test(value)) {
            value = `https://${value}`;
        }
        const url = new URL(value);
        if (!/github\.com$/i.test(url.hostname)) {
            return null;
        }
        const segments = url.pathname.split('/').filter(Boolean);
        if (segments.length < 2) {
            return null;
        }
        const owner = segments[0].trim();
        const name = segments[1].trim();
        if (!owner || !name) {
            return null;
        }
        return { owner, name };
    } catch (error) {
        return null;
    }
}

function handleRepoUrlChange(rawValue) {
    const parsed = parseRepositoryInput(rawValue);
    if (!parsed) {
        return;
    }

    const repoIdentifier = `${parsed.owner}/${parsed.name}`;
    const displayNameInput = document.getElementById('repoDisplayName');
    if (displayNameInput && !displayNameInput.value.trim()) {
        displayNameInput.value = repoIdentifier;
    }

    const categoryInput = document.getElementById('repoCategory');
    if (categoryInput && !categoryInput.value.trim()) {
        categoryInput.value = parsed.owner;
    }
}

async function loadRepositories() {
    const listContainer = document.getElementById('repository-list');

    try {
        const response = await fetch('/api/repositories?includeInactive=true&includeFilters=true');
        const data = await response.json();

        if (!response.ok || data.success === false) {
            const message = data && data.error ? data.error : `Failed to load repositories (HTTP ${response.status})`;
            throw new Error(message);
        }

        repositories = Array.isArray(data.repositories) ? data.repositories : [];
        repositoryStats = data.stats || null;

        renderRepositoryMetrics();
        renderRepositories();
    } catch (error) {
        console.error('Error loading repositories:', error);
        repositoryStats = null;
        renderRepositoryMetrics();

        if (listContainer) {
            listContainer.innerHTML = `
                <div class="col-12">
                    <div class="alert alert-danger">
                        ${escapeHtml(error.message || 'Failed to load repositories. Please check if the sync service is running.')}
                    </div>
                </div>
            `;
        }

        showError(error.message || 'Failed to load repositories. Please check if the sync service is running.');
    }
}

function renderRepositoryMetrics() {
    const metricsContainer = document.getElementById('repository-metrics');
    if (!metricsContainer) {
        return;
    }

    if (!repositoryStats) {
        metricsContainer.innerHTML = '';
        return;
    }

    const total = repositoryStats.total || 0;
    const active = repositoryStats.active || 0;
    const inactive = repositoryStats.inactive || 0;
    const issues = repositoryStats.issues || 0;
    const pullRequests = repositoryStats.pull_requests || 0;

    metricsContainer.innerHTML = `
        <div class="col-md-3 mb-3">
            <div class="card metric-card h-100">
                <div class="card-body text-center">
                    <div class="metric-label text-muted">Total Repositories</div>
                    <div class="metric-value">${total}</div>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="card metric-card h-100">
                <div class="card-body text-center">
                    <div class="metric-label text-muted">Active</div>
                    <div class="metric-value text-success">${active}</div>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="card metric-card h-100">
                <div class="card-body text-center">
                    <div class="metric-label text-muted">Inactive</div>
                    <div class="metric-value text-muted">${inactive}</div>
                </div>
            </div>
        </div>
        <div class="col-md-3 mb-3">
            <div class="card metric-card h-100">
                <div class="card-body text-center">
                    <div class="metric-label text-muted">Tracked Items</div>
                    <div class="metric-value">${issues + pullRequests}</div>
                    <div class="metric-subtext text-muted">${issues} issues • ${pullRequests} PRs</div>
                </div>
            </div>
        </div>
    `;
}

function renderRepositories() {
    const container = document.getElementById('repository-list');

    if (!container) {
        return;
    }

    if (!repositories || repositories.length === 0) {
        container.innerHTML = `
            <div class="col-12">
                <div class="text-center p-5">
                    <i class="bi bi-folder-x text-muted" style="font-size: 4rem;"></i>
                    <h4 class="mt-3 text-muted">No repositories configured</h4>
                    <p class="text-muted">Add your first repository to start syncing GitHub issues and pull requests.</p>
                    <button class="btn btn-primary" data-bs-toggle="modal" data-bs-target="#addRepoModal">
                        <i class="bi bi-plus-circle"></i> Add Repository
                    </button>
                </div>
            </div>
        `;
        return;
    }

    const sortedRepos = repositories
        .slice()
        .sort((a, b) => {
            const priorityA = Number(a.priority) || 99;
            const priorityB = Number(b.priority) || 99;
            if (priorityA !== priorityB) {
                return priorityA - priorityB;
            }
            return (a.repo || '').localeCompare(b.repo || '');
        });

    const repoCards = sortedRepos.map(rawRepo => {
        const repo = {
            ...rawRepo,
            repo: rawRepo.repo || '',
            display_name: rawRepo.display_name || rawRepo.repo || '—',
            main_category: rawRepo.main_category || 'Uncategorized',
            classification: rawRepo.classification || 'Other',
            language_group: rawRepo.language_group || rawRepo.classification || 'Other',
            issue_count: Number(rawRepo.issue_count) || 0,
            pr_count: Number(rawRepo.pr_count) || 0,
            is_active: rawRepo.is_active === true || rawRepo.is_active === 1
        };

        const isActive = repo.is_active;
        const statusIcon = isActive ? 'check-circle-fill text-success' : 'x-circle-fill text-danger';
        const status = isActive ? 'Active' : 'Inactive';

        const priorityValue = Number(repo.priority);
        const priorityInfo = PRIORITY_CONFIG[priorityValue] || {
            label: Number.isFinite(priorityValue) ? `Custom (${priorityValue})` : 'Unspecified',
            className: 'priority-custom',
            badgeClass: 'bg-secondary'
        };

        const languageKey = repo.language_group;
        const languageBadge = LANGUAGE_BADGE_CLASS[languageKey] || LANGUAGE_BADGE_CLASS.Other;

        const filters = repo.filters || {};
        const issueFilterSummary = escapeHtml(summarizeFilterConfiguration(filters.issues, 'issues'));
        const prFilterSummary = escapeHtml(summarizeFilterConfiguration(filters.pull_requests, 'prs'));

        const updatedAt = formatDate(repo.updated_at);
        const createdAt = formatDate(repo.created_at);
        const [repoOwner, repoName] = repo.repo.split('/');
        const repoLink = (repoOwner && repoName)
            ? `https://github.com/${encodeURIComponent(repoOwner)}/${encodeURIComponent(repoName)}`
            : '#';

        return `
            <div class="col-md-6 col-lg-4 mb-4">
                <div class="card repo-card h-100 ${priorityInfo.className}">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start mb-3">
                            <div>
                                <h5 class="card-title mb-0">
                                    <i class="bi bi-github"></i> ${escapeHtml(repo.repo)}
                                </h5>
                                <small class="text-muted">${escapeHtml(repo.display_name)}</small>
                            </div>
                            <span class="badge status-badge ${isActive ? 'bg-success' : 'bg-danger'}">
                                <i class="bi bi-${statusIcon}"></i> ${status}
                            </span>
                        </div>

                        <div class="mb-3">
                            <small class="text-muted">Category:</small>
                            <div class="fw-bold">${escapeHtml(repo.main_category)}</div>
                        </div>

                        <div class="mb-3 d-flex flex-wrap gap-2 align-items-center">
                            <span class="badge ${languageBadge}">
                                <i class="bi bi-translate"></i> ${escapeHtml(languageKey)}
                            </span>
                            <span class="badge ${priorityInfo.badgeClass}">
                                <i class="bi bi-bar-chart"></i> Priority: ${escapeHtml(priorityInfo.label)}
                            </span>
                            <span class="badge bg-light text-muted border">
                                Classification: ${escapeHtml(repo.classification)}
                            </span>
                        </div>

                        <div class="small text-muted mb-3">
                            <div>Issue filter: ${issueFilterSummary}</div>
                            <div>PR filter: ${prFilterSummary}</div>
                        </div>

                        <div class="row text-center mb-3">
                            <div class="col-6">
                                <div class="text-primary">
                                    <i class="bi bi-exclamation-circle"></i>
                                </div>
                                <small class="text-muted">Issues</small>
                                <div class="fw-bold">${repo.issue_count}</div>
                            </div>
                            <div class="col-6">
                                <div class="text-success">
                                    <i class="bi bi-git-pull-request"></i>
                                </div>
                                <small class="text-muted">PRs</small>
                                <div class="fw-bold">${repo.pr_count}</div>
                            </div>
                        </div>

                        <div class="small text-muted mb-3">
                            <div>Created: ${createdAt}</div>
                            <div>Last Updated: ${updatedAt}</div>
                        </div>

                        <div class="d-flex gap-2 mb-2">
                            <button class="btn btn-outline-primary btn-sm flex-fill" onclick="syncRepository('${repo.repo}')">
                                <i class="bi bi-arrow-clockwise"></i> Sync All
                            </button>
                            <button class="btn btn-outline-secondary btn-sm" onclick="syncRepositoryIssues('${repo.repo}')" title="Sync issues">
                                <i class="bi bi-exclamation-circle"></i>
                            </button>
                            <button class="btn btn-outline-success btn-sm" onclick="syncRepositoryPullRequests('${repo.repo}')" title="Sync pull requests">
                                <i class="bi bi-git-pull-request"></i>
                            </button>
                            <button class="btn btn-outline-danger btn-sm" onclick="removeRepository('${repo.repo}')" title="Remove repository">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>

                        <a class="btn btn-link btn-sm px-0" href="${repoLink}" target="_blank" rel="noopener">
                            View on GitHub
                        </a>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = repoCards;
}

function summarizeFilterConfiguration(config, type) {
    if (!config || typeof config !== 'object') {
        return type === 'prs' ? 'All pull requests' : 'All issues';
    }

    const parts = [];

    if (config.state) {
        parts.push(`State: ${config.state}`);
    }

    if (Array.isArray(config.labels) && config.labels.length > 0) {
        parts.push(`Labels: ${config.labels.join(', ')}`);
    }

    if (config.assignee) {
        parts.push(`Assignee: ${config.assignee}`);
    }

    if (config.milestone) {
        parts.push(`Milestone: ${config.milestone}`);
    }

    return parts.length ? parts.join(' • ') : 'Default filters';
}

async function addRepository() {
    const repoUrlInput = document.getElementById('repoUrl');
    const displayNameInput = document.getElementById('repoDisplayName');
    const categoryInput = document.getElementById('repoCategory');
    const classificationInput = document.getElementById('repoClassification');
    const priorityInput = document.getElementById('repoPriority');
    const activeInput = document.getElementById('repoActive');

    const parsedRepo = parseRepositoryInput(repoUrlInput ? repoUrlInput.value : '');
    if (!parsedRepo) {
        showError('Enter a valid GitHub repository URL like https://github.com/owner/repository.');
        if (repoUrlInput) {
            repoUrlInput.focus();
        }
        return;
    }

    const repoIdentifier = `${parsedRepo.owner}/${parsedRepo.name}`;
    const displayName = displayNameInput ? displayNameInput.value.trim() : '';
    const classification = classificationInput ? classificationInput.value : 'Other';
    const priorityValue = priorityInput ? parseInt(priorityInput.value, 10) : 3;
    const isActive = activeInput ? activeInput.checked : true;

    let mainCategory = categoryInput ? categoryInput.value.trim() : '';
    const resolvedDisplayName = displayName || repoIdentifier;
    if (!mainCategory) {
        mainCategory = parsedRepo.owner;
    }

    if (!mainCategory) {
        showError('Unable to determine a main category. Please provide one.');
        if (categoryInput) {
            categoryInput.focus();
        }
        return;
    }

    try {
        const payload = {
            repo: repoIdentifier,
            display_name: resolvedDisplayName,
            main_category: mainCategory,
            classification: classification || 'Other',
            priority: Number.isFinite(priorityValue) ? priorityValue : 3,
            is_active: isActive
        };

        const response = await fetch('/api/repositories', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        let result = null;
        try {
            result = await response.json();
        } catch (jsonError) {
            console.warn('Unable to parse add repository response as JSON', jsonError);
        }

        if (!response.ok || (result && result.success === false)) {
            const message = result && result.error ? result.error : `Failed to add repository (HTTP ${response.status})`;
            throw new Error(message);
        }

        const modal = bootstrap.Modal.getInstance(document.getElementById('addRepoModal'));
        if (modal) {
            modal.hide();
        }
        document.getElementById('add-repo-form').reset();
        loadRepositories();

        const successMessage = (result && result.message) ? result.message : `Repository ${repoIdentifier} added successfully!`;
        showSuccess(successMessage);
    } catch (error) {
        console.error('Error adding repository:', error);
        showError(error.message || 'Failed to add repository. Please try again.');
    }
}

async function removeRepository(repoPath) {
    if (!confirm(`Are you sure you want to remove ${repoPath}?`)) {
        return;
    }

    try {
        const response = await fetch(`/api/repositories/${encodeURIComponent(repoPath)}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            const message = payload.error || `Failed to remove repository (HTTP ${response.status})`;
            throw new Error(message);
        }

        loadRepositories();
        showSuccess(`Repository ${repoPath} removed successfully!`);
    } catch (error) {
        console.error('Error removing repository:', error);
        showError(error.message || 'Failed to remove repository. Please try again.');
    }
}

async function syncRepository(repoPath) {
    try {
        showInfo(`Starting full sync for ${repoPath}...`);

        const response = await fetch(`/api/sync/repositories/${encodeURIComponent(repoPath)}`, {
            method: 'POST'
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            const message = result.error || `Failed to sync repository (HTTP ${response.status})`;
            throw new Error(message);
        }

        showSuccess(`Sync completed for ${repoPath}!`);
        setTimeout(loadRepositories, 1000);
    } catch (error) {
        console.error('Error syncing repository:', error);
        showError(error.message || `Failed to sync ${repoPath}. Please try again.`);
    }
}

async function syncRepositoryIssues(repoPath) {
    await syncRepositoryByType(repoPath, 'issues');
}

async function syncRepositoryPullRequests(repoPath) {
    await syncRepositoryByType(repoPath, 'prs');
}

async function syncRepositoryByType(repoPath, type) {
    const endpoint = type === 'issues'
        ? `/api/sync/repositories/${encodeURIComponent(repoPath)}/issues`
        : `/api/sync/repositories/${encodeURIComponent(repoPath)}/prs`;

    try {
        showInfo(`Syncing ${type.toUpperCase()} for ${repoPath}...`);

        const response = await fetch(endpoint, { method: 'POST' });
        const result = await response.json().catch(() => ({}));

        if (!response.ok || result.success === false) {
            const message = result.error || `Failed to sync ${type} (HTTP ${response.status})`;
            throw new Error(message);
        }

        showSuccess(`${type.toUpperCase()} sync completed for ${repoPath}.`);
        setTimeout(loadRepositories, 1000);
    } catch (error) {
        console.error(`Error syncing ${type} for repository:`, error);
        showError(error.message || `Failed to sync ${type} for ${repoPath}. Please try again.`);
    }
}

function formatDate(value) {
    if (!value) {
        return '—';
    }

    try {
        const normalized = value.includes(' ') && !value.includes('T') ? value.replace(' ', 'T') : value;
        const date = new Date(normalized);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString();
    } catch (error) {
        return value;
    }
}

function showSuccess(message) {
    showAlert(message, 'success');
}

function showError(message) {
    showAlert(message, 'danger');
}

function showInfo(message) {
    showAlert(message, 'info');
}

function showAlert(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 1050; min-width: 300px;';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}
