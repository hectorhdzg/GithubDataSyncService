// Repository Management JavaScript

let repositories = [];
let repositoryLabelCache = {};

const PRIORITY_CONFIG = {
    1: { label: 'High', badgeClass: 'badge-priority-1' },
    2: { label: 'Medium', badgeClass: 'badge-priority-2' },
    3: { label: 'Low', badgeClass: 'badge-priority-3' }
};

let editingRepo = null;

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

    loadLabelsForAdd(repoIdentifier);
}

async function loadRepositories() {
    try {
        const response = await fetch('/api/repositories?includeInactive=true&includeFilters=true');
        const data = await response.json();

        if (!response.ok || data.success === false) {
            const message = data && data.error ? data.error : `Failed to load repositories (HTTP ${response.status})`;
            throw new Error(message);
        }

        repositories = Array.isArray(data.repositories) ? data.repositories : [];
        renderRepositories();
    } catch (error) {
        console.error('Error loading repositories:', error);
        document.getElementById('repository-list').innerHTML = `
            <tr><td colspan="9" class="text-center text-danger py-4">${escapeHtml(error.message || 'Failed to load repositories.')}</td></tr>
        `;
        showError(error.message || 'Failed to load repositories. Please check if the sync service is running.');
    }
}

function renderRepositories() {
    const tbody = document.getElementById('repository-list');
    const emptyState = document.getElementById('repository-empty');
    const table = document.getElementById('repository-table');

    if (!repositories || repositories.length === 0) {
        table.classList.add('d-none');
        emptyState.classList.remove('d-none');
        return;
    }

    table.classList.remove('d-none');
    emptyState.classList.add('d-none');

    const sortedRepos = repositories.slice().sort((a, b) => {
        const pA = Number(a.priority) || 99;
        const pB = Number(b.priority) || 99;
        if (pA !== pB) return pA - pB;
        return (a.repo || '').localeCompare(b.repo || '');
    });

    tbody.innerHTML = sortedRepos.map(rawRepo => {
        const repo = {
            ...rawRepo,
            repo: rawRepo.repo || '',
            display_name: rawRepo.display_name || rawRepo.repo || '',
            main_category: rawRepo.main_category || '',
            classification: rawRepo.classification || 'Other',
            issue_count: Number(rawRepo.issue_count) || 0,
            pr_count: Number(rawRepo.pr_count) || 0,
            is_active: rawRepo.is_active === true || rawRepo.is_active === 1
        };

        const priorityValue = Number(repo.priority);
        const priorityInfo = PRIORITY_CONFIG[priorityValue] || { label: 'N/A', badgeClass: 'bg-secondary' };
        const statusBadge = repo.is_active
            ? '<span class="badge bg-success">Active</span>'
            : '<span class="badge bg-secondary">Inactive</span>';
        const updatedAt = formatDate(repo.updated_at);
        const [owner, name] = repo.repo.split('/');
        const repoLink = (owner && name) ? `https://github.com/${encodeURIComponent(owner)}/${encodeURIComponent(name)}` : '#';

        return `
            <tr>
                <td>
                    <a href="${repoLink}" target="_blank" rel="noopener" class="text-decoration-none fw-semibold">${escapeHtml(repo.repo)}</a>
                    ${repo.display_name !== repo.repo ? `<br><small class="text-muted">${escapeHtml(repo.display_name)}</small>` : ''}
                </td>
                <td>${escapeHtml(repo.main_category)}</td>
                <td><span class="badge bg-dark">${escapeHtml(repo.classification)}</span></td>
                <td><span class="badge ${priorityInfo.badgeClass}">${escapeHtml(priorityInfo.label)}</span></td>
                <td>${repo.issue_count}</td>
                <td>${repo.pr_count}</td>
                <td>${statusBadge}</td>
                <td><small>${updatedAt}</small></td>
                <td class="text-end text-nowrap">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="openEditModal('${escapeHtml(repo.repo)}')" title="Edit">
                        <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-secondary me-1" onclick="syncRepository('${escapeHtml(repo.repo)}')" title="Sync">
                        <i class="bi bi-arrow-clockwise"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="removeRepository('${escapeHtml(repo.repo)}')" title="Delete">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');
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
            is_active: isActive,
            filters: buildFiltersPayloadFromInputs({ fallback: {} })
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

function openEditModal(repoPath) {
    editingRepo = repositories.find(r => r.repo === repoPath);
    if (!editingRepo) {
        showError('Unable to find repository details for editing.');
        return;
    }

    document.getElementById('editRepoId').value = editingRepo.repo;
    document.getElementById('editRepoDisplayName').value = editingRepo.display_name || editingRepo.repo;
    document.getElementById('editRepoCategory').value = editingRepo.main_category || '';
    document.getElementById('editRepoClassification').value = editingRepo.classification || 'Other';
    document.getElementById('editRepoPriority').value = editingRepo.priority || 3;
    document.getElementById('editRepoActive').checked = editingRepo.is_active === true || editingRepo.is_active === 1;

    // Pre-fill label inputs from stored filters (if any)
    const existingFilters = editingRepo.filters || {};
    setLabelInputsFromFilters(existingFilters, 'edit');

    // Populate label suggestions from cached GitHub labels
    populateLabelSuggestions(repoPath, 'edit');

    const modal = new bootstrap.Modal(document.getElementById('editRepoModal'));
    modal.show();
}

async function saveRepositoryEdits() {
    if (!editingRepo) {
        showError('No repository selected for edit.');
        return;
    }

    const displayName = document.getElementById('editRepoDisplayName').value.trim();
    const mainCategory = document.getElementById('editRepoCategory').value.trim();
    const classification = document.getElementById('editRepoClassification').value;
    const priorityValue = parseInt(document.getElementById('editRepoPriority').value, 10);
    const isActive = document.getElementById('editRepoActive').checked;

    if (!mainCategory) {
        showError('Main category is required.');
        return;
    }

    const payload = {
        display_name: displayName || editingRepo.repo,
        main_category: mainCategory,
        classification: classification || 'Other',
        priority: Number.isFinite(priorityValue) ? priorityValue : editingRepo.priority || 3,
        is_active: isActive,
        filters: buildFiltersPayloadFromInputs({
            fallback: editingRepo.filters || {},
            prefix: 'edit'
        })
    };

    try {
        const response = await fetch(`/api/repositories/${encodeURIComponent(editingRepo.repo)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok || result.success === false) {
            const message = result.error || `Failed to update repository (HTTP ${response.status})`;
            throw new Error(message);
        }

        const modalEl = document.getElementById('editRepoModal');
        const modal = bootstrap.Modal.getInstance(modalEl);
        if (modal) {
            modal.hide();
        }
        editingRepo = null;
        loadRepositories();
        showSuccess('Repository updated successfully.');
    } catch (error) {
        console.error('Error updating repository:', error);
        showError(error.message || 'Failed to update repository.');
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

function parseLabelInput(value) {
    if (!value) return [];
    return Array.from(new Set(
        value
            .split(/[,\n]/)
            .map(v => v.trim())
            .filter(Boolean)
    ));
}

function setLabelInputsFromFilters(filters, prefix) {
    const issuesInput = document.getElementById(`${prefix}IssuesLabels`);
    const prsInput = document.getElementById(`${prefix}PrLabels`);
    if (issuesInput && filters && filters.issues && Array.isArray(filters.issues.labels)) {
        issuesInput.value = filters.issues.labels.join(', ');
    }
    if (prsInput && filters && filters.pull_requests && Array.isArray(filters.pull_requests.labels)) {
        prsInput.value = filters.pull_requests.labels.join(', ');
    }
}

function buildFiltersPayloadFromInputs({ fallback = {}, prefix = '' }) {
    const filters = JSON.parse(JSON.stringify(fallback || {}));

    const issuesInput = document.getElementById(`${prefix}IssuesLabels`);
    const prsInput = document.getElementById(`${prefix}PrLabels`);

    const issuesLabels = issuesInput ? parseLabelInput(issuesInput.value) : [];
    const prLabels = prsInput ? parseLabelInput(prsInput.value) : [];

    if (!filters.issues) filters.issues = {};
    if (!filters.pull_requests) filters.pull_requests = {};

    if (issuesLabels.length > 0) {
        filters.issues.labels = issuesLabels;
    } else {
        delete filters.issues.labels;
    }

    if (prLabels.length > 0) {
        filters.pull_requests.labels = prLabels;
    } else {
        delete filters.pull_requests.labels;
    }

    return filters;
}

async function fetchRepositoryLabels(repoPath) {
    if (!repoPath) return [];
    if (repositoryLabelCache[repoPath]) {
        return repositoryLabelCache[repoPath];
    }

    try {
        const response = await fetch(`/api/repositories/${encodeURIComponent(repoPath)}/labels`);
        const result = await response.json().catch(() => ({}));
        if (response.ok && result.success && Array.isArray(result.labels)) {
            repositoryLabelCache[repoPath] = result.labels;
            return result.labels;
        }
    } catch (error) {
        console.warn('Unable to fetch labels for', repoPath, error);
    }
    return [];
}

async function populateLabelSuggestions(repoPath, prefix) {
    const labels = await fetchRepositoryLabels(repoPath);
    const dataList = document.getElementById(`${prefix}IssuesLabelsList`);
    const prDataList = document.getElementById(`${prefix}PrLabelsList`);

    const optionHtml = labels.map(label => `<option value="${escapeHtml(label.name || '')}"></option>`).join('');
    if (dataList) dataList.innerHTML = optionHtml;
    if (prDataList) prDataList.innerHTML = optionHtml;
}

async function loadLabelsForAdd(repoIdentifier) {
    await populateLabelSuggestions(repoIdentifier, 'add');
}
