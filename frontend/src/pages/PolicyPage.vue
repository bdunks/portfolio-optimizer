<template>
  <q-page
    class="workspace-page policy-page"
    :inert="saving || activating"
    :aria-busy="saving || activating"
  >
    <header class="page-header">
      <div>
        <p class="eyebrow">Allocation and tax profile</p>
        <h1>Allocation Policy</h1>
        <p class="page-subtitle">
          Configure versioned sleeve targets, replacement ETF candidates, holding overrides, and
          every persisted tax and batch setting. Target values remain exact decimal strings.
        </p>
      </div>
      <div class="page-actions">
        <button type="button" class="secondary-button" :disabled="loading" @click="refreshPolicy">
          {{ loading ? 'Loading…' : 'Refresh policy list' }}
        </button>
        <button type="button" class="primary-button" :disabled="!canSave" @click="saveDraft">
          {{ saving ? 'Saving…' : 'Save new draft revision' }}
        </button>
        <button
          type="button"
          class="secondary-button"
          :disabled="!canActivate"
          @click="activateSaved"
        >
          {{ activating ? 'Activating…' : 'Activate saved revision' }}
        </button>
      </div>
    </header>

    <p class="demo-notice" role="status">
      <strong>Local policy only.</strong> This editor makes no broker, OAuth, order-preview, or
      order submission calls. Tax rates are sent in API fraction units (for example, 0.25 means
      25%); all money, targets, and percentage values are preserved as entered.
    </p>

    <div class="error-stack" aria-label="Policy request errors">
      <ApiActionError
        :error="store.actionState.loadPolicy.error"
        title="Policy could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.loadPortfolio.error"
        title="Holdings for overrides could not be loaded"
      />
      <ApiActionError
        :error="store.actionState.savePolicyDraft.error"
        title="Policy draft could not be saved"
      />
      <ApiActionError
        :error="store.actionState.activatePolicy.error"
        title="Policy revision could not be activated"
      />
    </div>

    <section class="revision-panel" aria-labelledby="revision-title">
      <div class="section-heading">
        <div>
          <h2 id="revision-title">Policy revision</h2>
          <p class="section-subtitle">
            Revisions are immutable after save. Editing a revision always creates a new revision
            from the selected source; unsaved form edits are never replaced by refreshes.
          </p>
        </div>
        <span class="status-badge">{{ revisionStatus }}</span>
      </div>
      <div class="revision-controls">
        <label class="field revision-select">
          <span>Select source revision</span>
          <select
            v-model="revisionChoice"
            aria-label="Select policy source revision"
            @change="requestRevisionChange"
          >
            <option value="">New policy (no source revision)</option>
            <option v-for="revision in revisions" :key="revision.id" :value="revision.id">
              Revision {{ revision.revision_number }} · {{ revision.status }} · {{ revision.id }}
            </option>
          </select>
        </label>
        <div class="revision-id">
          <span>Source revision ID</span>
          <code>{{ sourceRevisionId ?? 'None — creating the first policy revision' }}</code>
        </div>
        <button type="button" class="text-button" :disabled="loading" @click="refreshPolicy">
          Load latest revisions
        </button>
      </div>
      <div v-if="pendingRevisionId" class="notice-card" role="alert">
        <p>There are unsaved edits. Loading another revision will discard them.</p>
        <div class="button-row">
          <button type="button" class="secondary-button" @click="cancelRevisionChange">
            Keep editing
          </button>
          <button type="button" class="danger-button" @click="discardAndLoadRevision">
            Discard edits and load
          </button>
        </div>
      </div>
      <p v-if="dirty" class="state-message" role="status">
        Unsaved changes. Activation is unavailable until this exact form is saved as a revision.
      </p>
      <p v-else-if="savedRevisionId" class="success-message" role="status">
        Current form matches saved revision {{ savedRevisionId }}. Only this saved content can be
        activated.
      </p>
      <p v-else-if="!loading && initialized" class="state-message">
        Save this configuration to create an immutable revision before activation.
      </p>
    </section>

    <section class="target-panel" aria-labelledby="target-title">
      <div class="section-heading">
        <div>
          <h2 id="target-title">Sleeves and allocation targets</h2>
          <p class="section-subtitle">
            Top-level targets and every populated nested allocation must total exactly 100%. Drift
            bands use percentage points. No tolerance, implicit cash sleeve, or normalization is
            applied. Transition progress uses an explicitly designated destination sub-sleeve and
            all descendants regardless of security type; it remains unavailable when no destination
            is configured.
          </p>
        </div>
        <button type="button" class="secondary-button" @click="addSleeve">+ Add sleeve</button>
      </div>
      <div v-if="targetIssues.length" class="validation-card" role="status" aria-live="polite">
        <strong>Target check — activation is not valid yet</strong>
        <ul>
          <li v-for="issue in targetIssues" :key="issue">{{ issue }}</li>
        </ul>
        <p>These client-side checks are guidance only; the backend response is authoritative.</p>
      </div>
      <div v-else class="success-card" role="status">
        Enabled top-level and nested target sums are exactly 100%.
      </div>
      <p v-if="deleteError && !pendingDeleteSleeve" class="inline-error" role="alert">
        {{ deleteError }}
      </p>
      <div class="table-scroll">
        <table class="editor-table sleeves-table">
          <thead>
            <tr>
              <th>Order / sleeve key</th>
              <th>Name</th>
              <th>Parent</th>
              <th>Target (%)</th>
              <th>Drift band (pp)</th>
              <th>Designations</th>
              <th>Enabled</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(sleeve, index) in sleeves"
              :key="`${sleeve.sleeve_key}-${index}`"
              :class="{ 'disabled-row': !sleeve.enabled }"
            >
              <td>
                <div class="order-tools">
                  <button
                    type="button"
                    class="icon-button"
                    :aria-label="`Move ${sleeve.display_name || 'sleeve'} up`"
                    :disabled="!canMoveSleeve(index, -1)"
                    @click="moveSleeve(index, -1)"
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    class="icon-button"
                    :aria-label="`Move ${sleeve.display_name || 'sleeve'} down`"
                    :disabled="!canMoveSleeve(index, 1)"
                    @click="moveSleeve(index, 1)"
                  >
                    ↓
                  </button>
                </div>
                <code class="sleeve-key">{{ sleeve.sleeve_key || 'new sleeve' }}</code>
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">Sleeve name</span
                  ><input
                    v-model="sleeve.display_name"
                    aria-label="Sleeve display name"
                    placeholder="Display name"
                /></label>
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">Parent sleeve</span>
                  <select v-model="sleeve.parent_sleeve_key" aria-label="Parent sleeve">
                    <option :value="null">Top level</option>
                    <option
                      v-for="parent in parentOptions(sleeve)"
                      :key="parent.sleeve_key"
                      :value="parent.sleeve_key"
                    >
                      {{ parent.display_name || parent.sleeve_key }}
                    </option>
                  </select>
                </label>
              </td>
              <td>
                <label class="compact-field target-input"
                  ><span class="sr-only">Target percent</span
                  ><input
                    v-model="sleeve.target_pct"
                    inputmode="decimal"
                    aria-label="Target percent"
                    placeholder="0"
                /></label>
              </td>
              <td>
                <label class="compact-field target-input"
                  ><span class="sr-only">Drift band percentage points</span
                  ><input
                    v-model="sleeve.drift_band_pp"
                    inputmode="decimal"
                    aria-label="Drift band in percentage points"
                    placeholder="0"
                /></label>
              </td>
              <td class="designation-cell">
                <label
                  ><input
                    type="checkbox"
                    :checked="sleeve.is_direct_index_container"
                    @change="setDirectIndexContainer(sleeve, $event)"
                  />
                  Direct-index container</label
                >
                <label
                  ><input v-model="sleeve.is_direct_index_sleeve" type="checkbox" /> Direct-index
                  sleeve</label
                >
                <label
                  ><input
                    type="checkbox"
                    aria-label="Transition destination sub-sleeve"
                    :checked="sleeve.is_transition_destination"
                    @change="setTransitionDestination(sleeve, $event)"
                  />
                  Transition destination sub-sleeve</label
                >
                <label><input v-model="sleeve.is_cash_sleeve" type="checkbox" /> Cash sleeve</label>
              </td>
              <td>
                <label class="toggle-field"
                  ><input
                    :checked="sleeve.enabled"
                    type="checkbox"
                    @change="setSleeveEnabled(sleeve, $event)"
                  /><span>{{ sleeve.enabled ? 'Enabled' : 'Disabled' }}</span></label
                >
                <label v-if="!sleeve.enabled" class="compact-field reassignment-field">
                  <span>Reassign held assets to</span>
                  <select
                    v-model="reassignments[sleeve.sleeve_key]"
                    :aria-label="`Reassign holdings from ${sleeve.display_name || sleeve.sleeve_key}`"
                  >
                    <option value="">Choose destination</option>
                    <option
                      v-for="target in reassignmentOptions(sleeve.sleeve_key)"
                      :key="target.sleeve_key"
                      :value="target.sleeve_key"
                    >
                      {{ target.display_name || target.sleeve_key }}
                    </option>
                  </select>
                </label>
              </td>
              <td>
                <button
                  type="button"
                  class="danger-button small-button"
                  @click="beginDeleteSleeve(sleeve.sleeve_key)"
                >
                  Delete
                </button>
              </td>
            </tr>
            <tr v-if="sleeves.length === 0">
              <td colspan="8" class="empty-cell">
                No sleeves configured. Add a sleeve and enter its policy values.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-if="pendingDeleteSleeve"
        class="delete-panel"
        role="group"
        aria-labelledby="delete-title"
      >
        <h3 id="delete-title">
          Delete {{ pendingDeleteSleeve.display_name || pendingDeleteSleeve.sleeve_key }}
        </h3>
        <p>
          Choose an enabled destination for any holdings currently assigned here. Reassignments are
          explicit; no holdings are silently orphaned.
        </p>
        <label v-if="heldInSleeve(pendingDeleteSleeve.sleeve_key).length" class="field">
          <span>Holding reassignment destination</span>
          <select v-model="deleteTargetKey" aria-label="Holding reassignment destination">
            <option value="">Choose destination</option>
            <option
              v-for="target in reassignmentOptions(pendingDeleteSleeve.sleeve_key)"
              :key="target.sleeve_key"
              :value="target.sleeve_key"
            >
              {{ target.display_name || target.sleeve_key }}
            </option>
          </select>
        </label>
        <div
          v-for="child in childrenOf(pendingDeleteSleeve.sleeve_key)"
          :key="child.sleeve_key"
          class="reparent-row"
        >
          <label class="field"
            ><span>Move child “{{ child.display_name || child.sleeve_key }}” under</span>
            <select
              v-model="childReparents[child.sleeve_key]"
              :aria-label="`New parent for ${child.display_name || child.sleeve_key}`"
            >
              <option value="">Choose new parent</option>
              <option :value="null">Top level</option>
              <option
                v-for="parent in reparentOptions(pendingDeleteSleeve.sleeve_key, child.sleeve_key)"
                :key="parent.sleeve_key"
                :value="parent.sleeve_key"
              >
                {{ parent.display_name || parent.sleeve_key }}
              </option>
            </select>
          </label>
        </div>
        <p v-if="deleteError" class="inline-error" role="alert">{{ deleteError }}</p>
        <div class="button-row">
          <button type="button" class="danger-button" @click="confirmDeleteSleeve">
            Confirm delete
          </button>
          <button type="button" class="text-button" @click="cancelDeleteSleeve">Cancel</button>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="etf-title">
      <div class="section-heading">
        <div>
          <h2 id="etf-title">Approved ETF replacement sets</h2>
          <p class="section-subtitle">
            Set ID groups candidate pairs or triplets; priority, suitability, enabled status, and
            sleeve assignments are explicit policy data. Distinct approved funds are a user
            assumption, not a wash-sale guarantee or automated exposure-equivalence check.
          </p>
        </div>
        <button type="button" class="secondary-button" @click="addSecurity">
          + Add ETF candidate
        </button>
      </div>
      <div class="table-scroll">
        <table class="editor-table securities-table">
          <thead>
            <tr>
              <th>Order</th>
              <th>Ticker</th>
              <th>Replacement set ID</th>
              <th>Priority</th>
              <th>Parent sleeve</th>
              <th>Sub-sleeve</th>
              <th>Exposure suitability (API note)</th>
              <th>Enabled</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(security, index) in allowedSecurities"
              :key="`${security.ticker}-${security.replacement_set_id}-${index}`"
            >
              <td>
                <div class="order-tools">
                  <button
                    type="button"
                    class="icon-button"
                    :aria-label="`Move ${security.ticker || 'candidate'} up`"
                    :disabled="!canMoveSecurity(index, -1)"
                    @click="moveSecurity(index, -1)"
                  >
                    ↑</button
                  ><button
                    type="button"
                    class="icon-button"
                    :aria-label="`Move ${security.ticker || 'candidate'} down`"
                    :disabled="!canMoveSecurity(index, 1)"
                    @click="moveSecurity(index, 1)"
                  >
                    ↓
                  </button>
                </div>
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">ETF ticker</span
                  ><input v-model="security.ticker" aria-label="ETF ticker" placeholder="Ticker"
                /></label>
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">Replacement set ID</span
                  ><input
                    v-model="security.replacement_set_id"
                    aria-label="Replacement set ID"
                    placeholder="Set ID"
                /></label>
              </td>
              <td>
                <label class="compact-field priority-input"
                  ><span class="sr-only">Candidate priority</span
                  ><input
                    v-model.number="security.priority"
                    type="number"
                    step="1"
                    aria-label="Candidate priority"
                /></label>
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">Candidate parent sleeve</span
                  ><select v-model="security.sleeve_key" aria-label="Candidate parent sleeve">
                    <option value="">Choose sleeve</option>
                    <option
                      v-for="sleeve in enabledTopLevelSleeves"
                      :key="sleeve.sleeve_key"
                      :value="sleeve.sleeve_key"
                    >
                      {{ sleeve.display_name || sleeve.sleeve_key }}
                    </option>
                  </select></label
                >
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">Candidate sub-sleeve</span
                  ><select v-model="security.sub_sleeve_key" aria-label="Candidate sub-sleeve">
                    <option :value="null">None</option>
                    <option
                      v-for="child in enabledChildren(security.sleeve_key)"
                      :key="child.sleeve_key"
                      :value="child.sleeve_key"
                    >
                      {{ child.display_name || child.sleeve_key }}
                    </option>
                  </select></label
                >
              </td>
              <td>
                <label class="compact-field"
                  ><span class="sr-only">Exposure suitability note</span
                  ><input
                    v-model="security.exposure_suitability"
                    aria-label="Exposure suitability note"
                    placeholder="Optional API text"
                /></label>
              </td>
              <td>
                <label class="toggle-field"
                  ><input v-model="security.enabled" type="checkbox" /><span>{{
                    security.enabled ? 'Enabled' : 'Disabled'
                  }}</span></label
                >
              </td>
              <td>
                <button
                  type="button"
                  class="danger-button small-button"
                  :aria-label="`Remove ${security.ticker || 'ETF candidate'}`"
                  @click="removeSecurity(index)"
                >
                  Remove
                </button>
              </td>
            </tr>
            <tr v-if="allowedSecurities.length === 0">
              <td colspan="9" class="empty-cell">
                No replacement candidates configured. Nothing is inferred or added automatically.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel" aria-labelledby="overrides-title">
      <div class="section-heading">
        <div>
          <h2 id="overrides-title">Explicit holding overrides</h2>
          <p class="section-subtitle">
            “Use default resolution” removes an override. The API resolves approved ETFs by
            configured assignment and individual equities plus VB/VXF by the direct-index container
            unless explicitly overridden; this page does not infer new assignments.
          </p>
        </div>
      </div>
      <p
        v-if="store.actionState.loadPortfolio.pending && !store.portfolio"
        class="state-message"
        role="status"
      >
        Loading the current single-account holding list…
      </p>
      <p v-else-if="!store.portfolio" class="empty-note">
        Current holdings are unavailable. Existing saved overrides remain editable below; no
        holdings are guessed.
      </p>
      <div class="table-scroll">
        <table class="editor-table override-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Current API resolution</th>
              <th>Explicit override</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="holding in overrideHoldings" :key="holding.ticker">
              <td>
                <strong>{{ holding.ticker }}</strong>
              </td>
              <td>{{ holding.currentLabel }}</td>
              <td>
                <label class="compact-field override-select"
                  ><span class="sr-only">Explicit override for {{ holding.ticker }}</span>
                  <select
                    :value="overrideTarget(holding.ticker)"
                    :aria-label="`Explicit override for ${holding.ticker}`"
                    @change="setOverrideTarget(holding.ticker, $event)"
                  >
                    <option value="">Use default resolution</option>
                    <option
                      v-if="currentOverrideTargetIsDisabled(holding.ticker)"
                      :value="overrideTarget(holding.ticker)"
                    >
                      Current assignment — disabled; choose a valid target or remove
                    </option>
                    <option
                      v-for="target in overrideOptions"
                      :key="target.sleeve_key"
                      :value="target.sleeve_key"
                    >
                      {{ target.display_name || target.sleeve_key }}
                    </option>
                  </select>
                </label>
              </td>
            </tr>
            <tr v-if="overrideHoldings.length === 0">
              <td colspan="3" class="empty-cell">
                No current holdings or explicit overrides have been returned.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel settings-panel" aria-labelledby="settings-title">
      <div class="section-heading">
        <div>
          <h2 id="settings-title">Tax &amp; Batch Settings</h2>
          <p class="section-subtitle">
            Blank nullable values are sent as null; blank required values are never guessed as zero.
            Amounts remain exact API decimal strings.
          </p>
        </div>
      </div>
      <div class="settings-group">
        <h3>Tax rates, carryforwards, and YTD realized amounts</h3>
        <p class="unit-note">
          ST/LT tax rates use fraction units (0–1); 0.25 means 25%. Missing rate stays null and
          makes tax estimates unavailable.
        </p>
        <div class="field-grid">
          <label class="field"
            ><span>Short-term marginal tax rate (fraction, nullable)</span
            ><input
              v-model="settings.short_term_tax_rate"
              inputmode="decimal"
              placeholder="Leave blank if unknown"
          /></label>
          <label class="field"
            ><span>Long-term marginal tax rate (fraction, nullable)</span
            ><input
              v-model="settings.long_term_tax_rate"
              inputmode="decimal"
              placeholder="Leave blank if unknown"
          /></label>
          <label class="field"
            ><span>ST loss carryforward (USD)</span
            ><input v-model="settings.st_loss_carryforward_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>LT loss carryforward (USD)</span
            ><input v-model="settings.lt_loss_carryforward_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>YTD realized ST gain / loss (USD)</span
            ><input v-model="settings.ytd_realized_st_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>YTD realized LT gain / loss (USD)</span
            ><input v-model="settings.ytd_realized_lt_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>YTD source (nullable)</span
            ><input v-model="settings.ytd_source" placeholder="Broker or manual profile source"
          /></label>
          <label class="field"
            ><span>YTD as-of date (nullable)</span><input v-model="settings.ytd_as_of" type="date"
          /></label>
        </div>
        <p class="unit-note">
          YTD source and date identify the returned YTD values. Enter explicit manual adjustments in
          the YTD fields; the editor does not combine broker and manual amounts.
        </p>
      </div>
      <div class="settings-group">
        <h3>Retained loss and gain / tax budgets</h3>
        <div class="field-grid">
          <label class="field"
            ><span>Target retained net loss (USD)</span
            ><input v-model="settings.target_retained_net_loss_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>Ordinary-income deduction limit (USD)</span
            ><input v-model="settings.ordinary_income_deduction_limit_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>Carryforward loss discount factor (fraction, 0–1)</span
            ><input v-model="settings.carryforward_loss_discount_factor" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>Incremental realized-gain budget (USD, nullable)</span
            ><input v-model="settings.gain_budget_usd" inputmode="decimal" placeholder="No limit"
          /></label>
          <label class="field"
            ><span>Maximum incremental estimated tax cost (USD, nullable)</span
            ><input
              v-model="settings.max_incremental_tax_cost_usd"
              inputmode="decimal"
              placeholder="No limit"
          /></label>
          <label class="field"
            ><span>ST gain limit (USD, nullable)</span
            ><input
              v-model="settings.st_gain_limit_usd"
              inputmode="decimal"
              placeholder="No separate limit"
          /></label>
          <label class="field"
            ><span>LT gain limit (USD, nullable)</span
            ><input
              v-model="settings.lt_gain_limit_usd"
              inputmode="decimal"
              placeholder="No separate limit"
          /></label>
          <label class="field"
            ><span>Budget period (API value)</span
            ><input v-model="settings.budget_period" placeholder="e.g. calendar_year"
          /></label>
        </div>
      </div>
      <div class="settings-group">
        <h3>Small-batch limits and trading preferences</h3>
        <div class="field-grid">
          <label class="field"
            ><span>Maximum sell tickers per batch</span
            ><input v-model="settings.max_sell_tickers_per_batch" inputmode="numeric"
          /></label>
          <label class="field"
            ><span>Maximum sell lots per batch</span
            ><input v-model="settings.max_sell_lots_per_batch" inputmode="numeric"
          /></label>
          <label class="field"
            ><span>Maximum total orders per batch</span
            ><input v-model="settings.max_total_orders_per_batch" inputmode="numeric"
          /></label>
          <label class="field"
            ><span>Maximum batch turnover (%)</span
            ><input v-model="settings.max_batch_turnover_pct" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>Minimum replacement BUY notional (USD)</span
            ><input v-model="settings.min_buy_order_notional_usd" inputmode="decimal"
          /></label>
          <label class="field"
            ><span>Cash reserve (USD)</span
            ><input v-model="settings.cash_reserve_usd" inputmode="decimal"
          /></label>
        </div>
        <div class="toggle-grid">
          <label class="field"
            ><span>Prefer ETF buys</span
            ><select v-model="settings.prefer_etf_buys">
              <option :value="null">Choose</option>
              <option :value="true">Enabled</option>
              <option :value="false">Disabled</option>
            </select></label
          >
          <label class="field"
            ><span>Allow appreciated-gain sales</span
            ><select v-model="settings.allow_gain_sales">
              <option :value="null">Choose</option>
              <option :value="true">Enabled</option>
              <option :value="false">Disabled</option>
            </select></label
          >
          <label class="field"
            ><span>Permit ETF harvesting</span
            ><select v-model="settings.permit_etf_harvest">
              <option :value="null">Choose</option>
              <option :value="true">Enabled</option>
              <option :value="false">Disabled</option>
            </select></label
          >
          <label class="field"
            ><span>Permit municipal-bond exit</span
            ><select v-model="settings.permit_muni_exit">
              <option :value="null">Choose</option>
              <option :value="true">Enabled</option>
              <option :value="false">Disabled</option>
            </select></label
          >
        </div>
        <p class="unit-note">
          No minimum SELL notional is configured here. The minimum notional applies only to
          replacement ETF BUY legs.
        </p>
      </div>
      <ul
        v-if="formIssues.length"
        class="form-issues"
        role="alert"
        aria-label="Form fields that must be completed before saving"
      >
        <li v-for="issue in formIssues" :key="issue">{{ issue }}</li>
      </ul>
    </section>

    <section class="activation-panel" aria-labelledby="activation-title">
      <div class="section-heading">
        <div>
          <h2 id="activation-title">Activation validation</h2>
          <p class="section-subtitle">
            Invalid exact target sums may be saved as drafts. Only a saved, unchanged revision can
            be activated; the backend remains authoritative.
          </p>
        </div>
        <span
          :class="['status-badge', activationIssues.length ? 'status-warning' : 'status-ready']"
          >{{ activationIssues.length ? 'Needs attention' : 'Target sums valid' }}</span
        >
      </div>
      <div v-if="activationIssues.length" class="validation-card" role="status">
        <strong>Activation errors for saved revision</strong>
        <ul>
          <li v-for="issue in activationIssues" :key="issue">{{ issue }}</li>
        </ul>
      </div>
      <p v-else class="success-card">
        No target-sum errors are currently reported. Other backend validation can still reject
        activation.
      </p>
      <p v-if="lastSavedRevision?.activation_errors?.length" class="api-errors-label">
        Backend activation_errors for revision {{ lastSavedRevision.id }}:
      </p>
      <ul
        v-if="lastSavedRevision?.activation_errors?.length"
        class="backend-errors"
        aria-label="Backend activation errors"
      >
        <li
          v-for="error in lastSavedRevision.activation_errors"
          :key="`${error.code}:${error.message}`"
        >
          <strong>{{ error.code }}</strong> — {{ error.message }}
        </li>
      </ul>
      <p class="capability-note">
        The accepted policy API persists sleeves, ETF candidate metadata, overrides and the fields
        shown above. It does not expose per-sleeve tracking/exposure tolerances, liquidity limits,
        or ETF-consolidation preference; those controls are not invented here. Portfolio
        look-through suitability is stored only as the API's user-entered text.
      </p>
    </section>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import type {
  AllowedSecurityInput,
  OverrideInput,
  PolicyDraftInput,
  PolicyRevisionResponse,
  PolicySettingsInput,
} from '@/types/api';
import ApiActionError from '@/components/ApiActionError.vue';
import { useWorkspaceStore } from '@/stores/workspace-store';
import {
  editableSleevesFromRevision,
  revisionToDraft,
  targetActivationIssues,
  type EditableSleeve,
} from './policy-form';

const store = useWorkspaceStore();
const emptySettings: PolicySettingsDraft = {
  short_term_tax_rate: '',
  long_term_tax_rate: '',
  st_loss_carryforward_usd: '',
  lt_loss_carryforward_usd: '',
  ytd_realized_st_usd: '',
  ytd_realized_lt_usd: '',
  ytd_source: '',
  ytd_as_of: '',
  target_retained_net_loss_usd: '',
  ordinary_income_deduction_limit_usd: '',
  carryforward_loss_discount_factor: '',
  gain_budget_usd: '',
  max_incremental_tax_cost_usd: '',
  st_gain_limit_usd: '',
  lt_gain_limit_usd: '',
  budget_period: '',
  max_sell_tickers_per_batch: '',
  max_sell_lots_per_batch: '',
  max_total_orders_per_batch: '',
  max_batch_turnover_pct: '',
  min_buy_order_notional_usd: '',
  cash_reserve_usd: '',
  prefer_etf_buys: null,
  allow_gain_sales: null,
  permit_etf_harvest: null,
  permit_muni_exit: null,
};

type PolicySettingsDraft = {
  short_term_tax_rate: string | null;
  long_term_tax_rate: string | null;
  st_loss_carryforward_usd: string | null;
  lt_loss_carryforward_usd: string | null;
  ytd_realized_st_usd: string | null;
  ytd_realized_lt_usd: string | null;
  ytd_source: string | null;
  ytd_as_of: string | null;
  target_retained_net_loss_usd: string | null;
  ordinary_income_deduction_limit_usd: string | null;
  carryforward_loss_discount_factor: string | null;
  gain_budget_usd: string | null;
  max_incremental_tax_cost_usd: string | null;
  st_gain_limit_usd: string | null;
  lt_gain_limit_usd: string | null;
  budget_period: string | null;
  max_sell_tickers_per_batch: string;
  max_sell_lots_per_batch: string;
  max_total_orders_per_batch: string;
  max_batch_turnover_pct: string | null;
  min_buy_order_notional_usd: string | null;
  cash_reserve_usd: string | null;
  prefer_etf_buys: boolean | null;
  allow_gain_sales: boolean | null;
  permit_etf_harvest: boolean | null;
  permit_muni_exit: boolean | null;
};

const settings = reactive<PolicySettingsDraft>({ ...emptySettings });
const sleeves = ref<EditableSleeve[]>([]);
const allowedSecurities = ref<AllowedSecurityInput[]>([]);
const overrides = ref<OverrideInput[]>([]);
const reassignments = reactive<Record<string, string>>({});
const sourceRevisionId = ref<string | null>(null);
const selectedRevisionId = ref<string | null>(null);
const revisionChoice = ref('');
const savedRevisionId = ref<string | null>(null);
const lastSavedRevision = ref<PolicyRevisionResponse | null>(null);
const baselineSignature = ref('');
const pendingRevisionId = ref<string | null>(null);
const deleteSleeveKey = ref<string | null>(null);
const deleteTargetKey = ref('');
const childReparents = reactive<Record<string, string | null>>({});
const deleteError = ref('');
const initialized = ref(false);
const nextSleeveNumber = ref(1);

const revisions = computed(() => {
  const policy = store.policy;
  if (!policy) return [];
  const all = [...policy.superseded, ...(policy.active ? [policy.active] : []), ...policy.drafts];
  return all
    .filter(
      (revision, index) => all.findIndex((candidate) => candidate.id === revision.id) === index,
    )
    .sort((left, right) => left.revision_number - right.revision_number);
});
const portfolio = computed(() => (store.portfolio?.status === 'ready' ? store.portfolio : null));
const currentSignature = computed(() =>
  JSON.stringify({
    settings,
    sleeves: sleeves.value,
    allowedSecurities: allowedSecurities.value,
    overrides: overrides.value,
    reassignments,
  }),
);
const dirty = computed(() => currentSignature.value !== baselineSignature.value);
const targetIssues = computed(() => targetActivationIssues(sleeves.value));
const savedBackendIssues = computed(() => lastSavedRevision.value?.activation_errors ?? []);
const activationIssues = computed(() => [
  ...targetIssues.value,
  ...savedBackendIssues.value.map((error) => `${error.code}: ${error.message}`),
]);
const revisionStatus = computed(() => {
  if (lastSavedRevision.value?.status === 'ACTIVE')
    return `ACTIVE · revision ${lastSavedRevision.value.revision_number}`;
  if (savedRevisionId.value)
    return `Saved · revision ${lastSavedRevision.value?.revision_number ?? savedRevisionId.value}`;
  if (sourceRevisionId.value)
    return `Editing source ${selectedRevisionId.value ?? sourceRevisionId.value}`;
  return initialized.value ? 'New unsaved policy' : 'Loading policy';
});
const loading = computed(
  () => store.actionState.loadPolicy.pending || store.actionState.loadPortfolio.pending,
);
const saving = computed(() => store.actionState.savePolicyDraft.pending);
const activating = computed(() => store.actionState.activatePolicy.pending);

const enabledSleeves = computed(() => sleeves.value.filter((sleeve) => sleeve.enabled !== false));
const enabledTopLevelSleeves = computed(() =>
  enabledSleeves.value.filter((sleeve) => !sleeve.parent_sleeve_key),
);
const overrideOptions = computed(() => enabledSleeves.value);
const formIssues = computed(() => {
  const issues: string[] = [];
  const requiredDecimals: Array<[string, string | null]> = [
    ['ST loss carryforward', settings.st_loss_carryforward_usd],
    ['LT loss carryforward', settings.lt_loss_carryforward_usd],
    ['YTD realized ST', settings.ytd_realized_st_usd],
    ['YTD realized LT', settings.ytd_realized_lt_usd],
    ['retained net loss target', settings.target_retained_net_loss_usd],
    ['ordinary-income deduction limit', settings.ordinary_income_deduction_limit_usd],
    ['carryforward discount factor', settings.carryforward_loss_discount_factor],
    ['maximum batch turnover', settings.max_batch_turnover_pct],
    ['minimum replacement BUY notional', settings.min_buy_order_notional_usd],
    ['cash reserve', settings.cash_reserve_usd],
  ];
  for (const [label, value] of requiredDecimals) {
    if (!value?.trim()) issues.push(`${label} is required; blank values are not changed to zero.`);
    else if (!DECIMAL_PATTERN.test(value.trim()))
      issues.push(`${label} must be an exact decimal string.`);
  }
  for (const [label, value] of [
    ['maximum sell tickers', settings.max_sell_tickers_per_batch],
    ['maximum sell lots', settings.max_sell_lots_per_batch],
    ['maximum total orders', settings.max_total_orders_per_batch],
  ] as const) {
    if (
      !value.trim() ||
      !POSITIVE_INTEGER_PATTERN.test(value.trim()) ||
      !Number.isSafeInteger(Number(value.trim()))
    )
      issues.push(`${label} must be a positive safe whole number.`);
  }
  for (const [label, value] of [
    ['ST tax rate', settings.short_term_tax_rate],
    ['LT tax rate', settings.long_term_tax_rate],
    ['gain budget', settings.gain_budget_usd],
    ['maximum tax cost', settings.max_incremental_tax_cost_usd],
    ['ST gain limit', settings.st_gain_limit_usd],
    ['LT gain limit', settings.lt_gain_limit_usd],
  ] as const) {
    if (value?.trim() && !DECIMAL_PATTERN.test(value.trim()))
      issues.push(`${label} must be an exact decimal string or blank (null).`);
  }
  if (settings.ytd_as_of?.trim() && !/^\d{4}-\d{2}-\d{2}$/.test(settings.ytd_as_of.trim()))
    issues.push('YTD as-of must be a date or blank (null).');
  if (!settings.budget_period?.trim()) issues.push('Budget period is required.');
  if (
    [
      settings.prefer_etf_buys,
      settings.allow_gain_sales,
      settings.permit_etf_harvest,
      settings.permit_muni_exit,
    ].some((value) => value === null)
  )
    issues.push('Choose each policy rule toggle explicitly.');
  if (
    sleeves.value.some(
      (sleeve) =>
        !sleeve.sleeve_key.trim() ||
        !sleeve.display_name.trim() ||
        !sleeve.target_pct.trim() ||
        !sleeve.drift_band_pp.trim(),
    )
  )
    issues.push('Each sleeve needs a key, display name, target, and drift band before saving.');
  if (!unique(sleeves.value.map((sleeve) => sleeve.sleeve_key.trim())))
    issues.push('Sleeve keys must be unique.');
  if (
    sleeves.value.some(
      (sleeve) =>
        sleeve.parent_sleeve_key &&
        !sleeves.value.some((candidate) => candidate.sleeve_key === sleeve.parent_sleeve_key),
    )
  )
    issues.push('Every nested sleeve must reference a sleeve in this draft.');
  if (
    sleeves.value.some(
      (sleeve) =>
        !DECIMAL_PATTERN.test(sleeve.target_pct.trim()) ||
        !DECIMAL_PATTERN.test(sleeve.drift_band_pp.trim()),
    )
  )
    issues.push(
      'Sleeve targets and drift bands must be exact decimal strings; valid but non-100% targets remain savable.',
    );
  if (
    allowedSecurities.value.some(
      (security) =>
        !security.ticker.trim() ||
        !security.sleeve_key.trim() ||
        !security.replacement_set_id?.trim(),
    )
  )
    issues.push(
      'Each ETF candidate needs a ticker, parent sleeve, and replacement-set ID before saving.',
    );
  if (allowedSecurities.value.some((security) => !Number.isSafeInteger(security.priority)))
    issues.push('ETF candidate priorities must be whole numbers.');
  if (
    allowedSecurities.value.some(
      (security) =>
        security.sub_sleeve_key &&
        !sleeves.value.some(
          (sleeve) =>
            sleeve.sleeve_key === security.sub_sleeve_key &&
            sleeve.parent_sleeve_key === security.sleeve_key,
        ),
    )
  )
    issues.push('Each ETF sub-sleeve must be a direct child of its selected parent sleeve.');
  if (overrides.value.some((override) => !override.ticker.trim() || !override.sleeve_key.trim()))
    issues.push('Each explicit holding override needs a ticker and destination sleeve.');
  if (
    overrides.value.some((override) => {
      const destination = sleeves.value.find(
        (sleeve) => sleeve.sleeve_key === (override.sub_sleeve_key ?? override.sleeve_key),
      );
      return (
        !destination ||
        destination.enabled === false ||
        (override.sub_sleeve_key && destination.parent_sleeve_key !== override.sleeve_key)
      );
    })
  )
    issues.push(
      'Explicit overrides must target an enabled sleeve (and any sub-sleeve must be its direct child).',
    );
  for (const sleeve of sleeves.value.filter((item) => item.enabled === false)) {
    if (
      heldInSleeve(sleeve.sleeve_key).some(
        (holding) => !overrides.value.some((override) => override.ticker === holding.ticker),
      ) &&
      !reassignments[sleeve.sleeve_key]
    )
      issues.push(
        `Choose a holding reassignment for disabled sleeve “${sleeve.display_name || sleeve.sleeve_key}”.`,
      );
  }
  return [...new Set(issues)];
});
const canSave = computed(
  () => initialized.value && formIssues.value.length === 0 && !saving.value && !activating.value,
);
const canActivate = computed(
  () =>
    !dirty.value &&
    !!savedRevisionId.value &&
    !activationIssues.value.length &&
    !saving.value &&
    !activating.value,
);
const overrideHoldings = computed(() => {
  const holdings =
    portfolio.value?.positions.map((position) => ({
      ticker: position.ticker,
      currentLabel: position.sub_sleeve_key
        ? `${position.sleeve_key} → ${position.sub_sleeve_key}`
        : (position.sleeve_key ?? 'No API sleeve resolution'),
    })) ?? [];
  const present = new Set(holdings.map((holding) => holding.ticker));
  for (const override of overrides.value) {
    if (!present.has(override.ticker))
      holdings.push({
        ticker: override.ticker,
        currentLabel: 'Override returned by policy API; holding not in current portfolio response',
      });
  }
  return holdings;
});
const pendingDeleteSleeve = computed(
  () => sleeves.value.find((sleeve) => sleeve.sleeve_key === deleteSleeveKey.value) ?? null,
);

const DECIMAL_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/;
const POSITIVE_INTEGER_PATTERN = /^[1-9]\d*$/;

function unique(values: string[]): boolean {
  return new Set(values).size === values.length;
}

function formSignature(): string {
  return JSON.stringify({
    settings,
    sleeves: sleeves.value,
    allowedSecurities: allowedSecurities.value,
    overrides: overrides.value,
    reassignments,
  });
}

function blankDraft(): void {
  Object.assign(settings, { ...emptySettings });
  sleeves.value = [];
  allowedSecurities.value = [];
  overrides.value = [];
  for (const key of Object.keys(reassignments)) delete reassignments[key];
  sourceRevisionId.value = null;
  selectedRevisionId.value = null;
  revisionChoice.value = '';
  savedRevisionId.value = null;
  lastSavedRevision.value = null;
  baselineSignature.value = formSignature();
  initialized.value = true;
}

function hydrateRevision(revision: PolicyRevisionResponse): void {
  const draft = revisionToDraft(revision);
  Object.assign(settings, {
    ...emptySettings,
    ...draft.settings,
    max_sell_tickers_per_batch: String(revision.settings.max_sell_tickers_per_batch),
    max_sell_lots_per_batch: String(revision.settings.max_sell_lots_per_batch),
    max_total_orders_per_batch: String(revision.settings.max_total_orders_per_batch),
    ytd_source: revision.settings.ytd_source ?? '',
    ytd_as_of: revision.settings.ytd_as_of ?? '',
  });
  sleeves.value = editableSleevesFromRevision(revision.sleeves);
  allowedSecurities.value = revision.allowed_securities.map((security) => ({ ...security }));
  overrides.value = revision.overrides.map((override) => ({ ...override }));
  for (const key of Object.keys(reassignments)) delete reassignments[key];
  sourceRevisionId.value = revision.id;
  selectedRevisionId.value = revision.id;
  revisionChoice.value = revision.id;
  savedRevisionId.value = revision.status === 'DRAFT' ? revision.id : null;
  lastSavedRevision.value = revision.status === 'DRAFT' ? revision : null;
  baselineSignature.value = formSignature();
  pendingRevisionId.value = null;
  initialized.value = true;
}

function initializeFromWorkspace(): void {
  if (initialized.value) return;
  const preferred =
    [...(store.policy?.drafts ?? [])].at(-1) ??
    store.policy?.active ??
    [...(store.policy?.superseded ?? [])].at(-1);
  if (preferred) hydrateRevision(preferred);
  else blankDraft();
}

async function loadInitial(): Promise<void> {
  const tasks: Promise<unknown>[] = [];
  if (!store.policy) tasks.push(store.loadPolicy());
  if (!store.portfolio) tasks.push(store.loadPortfolio());
  if (tasks.length) await Promise.allSettled(tasks);
  initializeFromWorkspace();
}

async function refreshPolicy(): Promise<void> {
  await store.loadPolicy().catch(() => undefined);
  // Loading revisions updates only the store list. The user's current form is intentionally untouched.
}

function requestRevisionChange(): void {
  if (!revisionChoice.value) {
    if (dirty.value) {
      pendingRevisionId.value = '__new__';
      revisionChoice.value = selectedRevisionId.value ?? '';
    } else blankDraft();
    return;
  }
  if (revisionChoice.value === selectedRevisionId.value) return;
  if (dirty.value) {
    pendingRevisionId.value = revisionChoice.value;
    revisionChoice.value = selectedRevisionId.value ?? '';
    return;
  }
  const revision = revisions.value.find((item) => item.id === revisionChoice.value);
  if (revision) hydrateRevision(revision);
}

function cancelRevisionChange(): void {
  pendingRevisionId.value = null;
  revisionChoice.value = selectedRevisionId.value ?? '';
}

function discardAndLoadRevision(): void {
  if (pendingRevisionId.value === '__new__') {
    blankDraft();
    return;
  }
  const revision = revisions.value.find((item) => item.id === pendingRevisionId.value);
  if (revision) hydrateRevision(revision);
  else cancelRevisionChange();
}

function settingsPayload(): PolicySettingsInput {
  const nullable = (value: string | null): string | null => (!value?.trim() ? null : value);
  return {
    short_term_tax_rate: nullable(settings.short_term_tax_rate),
    long_term_tax_rate: nullable(settings.long_term_tax_rate),
    st_loss_carryforward_usd: settings.st_loss_carryforward_usd ?? '',
    lt_loss_carryforward_usd: settings.lt_loss_carryforward_usd ?? '',
    ytd_realized_st_usd: settings.ytd_realized_st_usd ?? '',
    ytd_realized_lt_usd: settings.ytd_realized_lt_usd ?? '',
    ytd_source: nullable(settings.ytd_source),
    ytd_as_of: nullable(settings.ytd_as_of),
    target_retained_net_loss_usd: settings.target_retained_net_loss_usd ?? '',
    ordinary_income_deduction_limit_usd: settings.ordinary_income_deduction_limit_usd ?? '',
    carryforward_loss_discount_factor: settings.carryforward_loss_discount_factor ?? '',
    gain_budget_usd: nullable(settings.gain_budget_usd),
    max_incremental_tax_cost_usd: nullable(settings.max_incremental_tax_cost_usd),
    st_gain_limit_usd: nullable(settings.st_gain_limit_usd),
    lt_gain_limit_usd: nullable(settings.lt_gain_limit_usd),
    budget_period: settings.budget_period ?? '',
    max_sell_tickers_per_batch: Number(settings.max_sell_tickers_per_batch),
    max_sell_lots_per_batch: Number(settings.max_sell_lots_per_batch),
    max_total_orders_per_batch: Number(settings.max_total_orders_per_batch),
    max_batch_turnover_pct: settings.max_batch_turnover_pct ?? '',
    min_buy_order_notional_usd: settings.min_buy_order_notional_usd ?? '',
    cash_reserve_usd: settings.cash_reserve_usd ?? '',
    prefer_etf_buys: settings.prefer_etf_buys ?? false,
    allow_gain_sales: settings.allow_gain_sales ?? false,
    permit_etf_harvest: settings.permit_etf_harvest ?? false,
    permit_muni_exit: settings.permit_muni_exit ?? false,
  };
}

function payloadForSave(): PolicyDraftInput {
  return {
    source_revision_id: sourceRevisionId.value,
    settings: settingsPayload(),
    sleeves: sleeves.value.map((sleeve, index) => ({ ...sleeve, sort_order: index })),
    allowed_securities: allowedSecurities.value.map((security) => ({
      ...security,
      exposure_suitability: !security.exposure_suitability?.trim()
        ? null
        : security.exposure_suitability,
    })),
    overrides: overrides.value.map((override) => ({ ...override })),
    reassignments: Object.fromEntries(
      Object.entries(reassignments).filter(([, target]) => !!target),
    ),
  };
}

function sameOverride(left: OverrideInput | undefined, right: OverrideInput | undefined): boolean {
  if (!left || !right) return left === right;
  return (
    left.ticker === right.ticker &&
    left.sleeve_key === right.sleeve_key &&
    (left.sub_sleeve_key ?? null) === (right.sub_sleeve_key ?? null)
  );
}

function reconcileSavedOverrides(
  submitted: readonly OverrideInput[],
  current: readonly OverrideInput[],
  returned: readonly PolicyRevisionResponse['overrides'][number][],
): OverrideInput[] {
  const submittedByTicker = new Map(submitted.map((override) => [override.ticker, override]));
  const currentByTicker = new Map(current.map((override) => [override.ticker, override]));
  const returnedTickers = new Set(returned.map((override) => override.ticker));
  const reconciled = returned.flatMap((serverOverride) => {
    const currentOverride = currentByTicker.get(serverOverride.ticker);
    const submittedOverride = submittedByTicker.get(serverOverride.ticker);
    return sameOverride(currentOverride, submittedOverride)
      ? [{ ...serverOverride }]
      : currentOverride
        ? [{ ...currentOverride }]
        : [];
  });

  for (const currentOverride of current) {
    if (
      !returnedTickers.has(currentOverride.ticker) &&
      !sameOverride(currentOverride, submittedByTicker.get(currentOverride.ticker))
    )
      reconciled.push({ ...currentOverride });
  }
  return reconciled;
}

async function saveDraft(): Promise<void> {
  if (!canSave.value) return;
  const payload = payloadForSave();
  const savedSnapshot = formSignature();
  const savedState = JSON.parse(savedSnapshot) as {
    overrides: OverrideInput[];
    reassignments: Record<string, string>;
  };
  try {
    const revision = await store.savePolicyDraft(payload);
    overrides.value = reconcileSavedOverrides(
      payload.overrides ?? [],
      overrides.value,
      revision.overrides,
    );
    for (const [key, target] of Object.entries(savedState.reassignments)) {
      if (reassignments[key] === target) delete reassignments[key];
    }
    sourceRevisionId.value = revision.id;
    selectedRevisionId.value = revision.id;
    revisionChoice.value = revision.id;
    savedRevisionId.value = revision.id;
    lastSavedRevision.value = revision;
    savedState.overrides = revision.overrides.map((override) => ({ ...override }));
    savedState.reassignments = {};
    baselineSignature.value = JSON.stringify(savedState);
  } catch {
    // Structured error remains visible through ApiActionError.
  }
}

async function activateSaved(): Promise<void> {
  if (!canActivate.value || !savedRevisionId.value) return;
  try {
    const activated = await store.activatePolicy(savedRevisionId.value);
    lastSavedRevision.value = activated;
    savedRevisionId.value = null;
    sourceRevisionId.value = activated.id;
    selectedRevisionId.value = activated.id;
    revisionChoice.value = activated.id;
  } catch {
    // Backend validation and structured error remain visible; no unsaved form is activated.
  }
}

function addSleeve(): void {
  let key: string;
  do {
    key = `sleeve-new-${nextSleeveNumber.value++}`;
  } while (sleeves.value.some((sleeve) => sleeve.sleeve_key === key));

  sleeves.value.push({
    sleeve_key: key,
    display_name: '',
    sort_order: sleeves.value.length,
    parent_sleeve_key: null,
    target_pct: '',
    drift_band_pp: '',
    is_direct_index_container: false,
    is_direct_index_sleeve: false,
    is_transition_destination: false,
    is_cash_sleeve: false,
    enabled: true,
  });
}
function hasEnabledChild(key: string): boolean {
  return sleeves.value.some(
    (sleeve) => sleeve.enabled !== false && sleeve.parent_sleeve_key === key,
  );
}

function setSleeveEnabled(sleeve: EditableSleeve, event: Event): void {
  const enabled = (event.target as HTMLInputElement).checked;
  if (!enabled && hasEnabledChild(sleeve.sleeve_key)) {
    (event.target as HTMLInputElement).checked = true;
    deleteError.value = 'Disable or reparent enabled child sleeves before disabling this parent.';
    return;
  }
  sleeve.enabled = enabled;
  if (enabled) delete reassignments[sleeve.sleeve_key];
  deleteError.value = '';
}

function setDirectIndexContainer(sleeve: EditableSleeve, event: Event): void {
  const enabled = (event.target as HTMLInputElement).checked;
  for (const candidate of sleeves.value) candidate.is_direct_index_container = false;
  sleeve.is_direct_index_container = enabled;
}

function setTransitionDestination(sleeve: EditableSleeve, event: Event): void {
  const enabled = (event.target as HTMLInputElement).checked;
  for (const candidate of sleeves.value) candidate.is_transition_destination = false;
  sleeve.is_transition_destination = enabled;
}

function childrenOf(key: string): EditableSleeve[] {
  return sleeves.value.filter((sleeve) => sleeve.parent_sleeve_key === key);
}

function parentOptions(sleeve: EditableSleeve): EditableSleeve[] {
  return enabledSleeves.value.filter(
    (candidate) =>
      candidate.sleeve_key !== sleeve.sleeve_key &&
      !isDescendant(candidate.sleeve_key, sleeve.sleeve_key),
  );
}

function isDescendant(candidateKey: string, ancestorKey: string): boolean {
  let current = sleeves.value.find((sleeve) => sleeve.sleeve_key === candidateKey);
  while (current?.parent_sleeve_key) {
    if (current.parent_sleeve_key === ancestorKey) return true;
    current = sleeves.value.find((sleeve) => sleeve.sleeve_key === current?.parent_sleeve_key);
  }
  return false;
}

function sleeveSiblingTargetIndex(index: number, direction: -1 | 1): number | null {
  const sleeve = sleeves.value[index];
  if (!sleeve) return null;
  const siblings = sleeves.value
    .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
    .filter(({ candidate }) => candidate.parent_sleeve_key === sleeve.parent_sleeve_key);
  const siblingPosition = siblings.findIndex(({ candidateIndex }) => candidateIndex === index);
  return siblings[siblingPosition + direction]?.candidateIndex ?? null;
}

function canMoveSleeve(index: number, direction: -1 | 1): boolean {
  return sleeveSiblingTargetIndex(index, direction) !== null;
}

function moveSleeve(index: number, direction: -1 | 1): void {
  const targetIndex = sleeveSiblingTargetIndex(index, direction);
  if (targetIndex === null) return;
  [sleeves.value[index], sleeves.value[targetIndex]] = [
    sleeves.value[targetIndex]!,
    sleeves.value[index]!,
  ];
}

function heldInSleeve(key: string): Array<{ ticker: string }> {
  return (
    portfolio.value?.positions.filter(
      (position) => position.sleeve_key === key || position.sub_sleeve_key === key,
    ) ?? []
  );
}

function reassignmentOptions(excludedKey: string): EditableSleeve[] {
  return enabledSleeves.value.filter((sleeve) => sleeve.sleeve_key !== excludedKey);
}

function beginDeleteSleeve(key: string): void {
  deleteSleeveKey.value = key;
  deleteTargetKey.value = '';
  deleteError.value = '';
  for (const child of childrenOf(key)) childReparents[child.sleeve_key] = '';
}

function reparentOptions(deletingKey: string, childKey: string): EditableSleeve[] {
  return enabledTopLevelSleeves.value.filter(
    (sleeve) =>
      sleeve.sleeve_key !== deletingKey &&
      sleeve.sleeve_key !== childKey &&
      !isDescendant(sleeve.sleeve_key, childKey),
  );
}

function confirmDeleteSleeve(): void {
  const key = deleteSleeveKey.value;
  if (!key) return;
  const children = childrenOf(key);
  if (children.some((child) => childReparents[child.sleeve_key] === '')) {
    deleteError.value = 'Choose a new parent or top-level placement for every child sleeve.';
    return;
  }
  const holdings = heldInSleeve(key);
  if (holdings.length && !deleteTargetKey.value) {
    deleteError.value =
      'Choose an enabled holding reassignment destination before deleting this sleeve.';
    return;
  }
  if (holdings.length) reassignments[key] = deleteTargetKey.value;
  else delete reassignments[key];
  for (const child of children) child.parent_sleeve_key = childReparents[child.sleeve_key] || null;
  sleeves.value = sleeves.value.filter((sleeve) => sleeve.sleeve_key !== key);

  delete childReparents[key];
  deleteSleeveKey.value = null;
  deleteError.value = '';
}

function cancelDeleteSleeve(): void {
  deleteSleeveKey.value = null;
  deleteTargetKey.value = '';
  deleteError.value = '';
}

function enabledChildren(parentKey: string): EditableSleeve[] {
  return enabledSleeves.value.filter((sleeve) => sleeve.parent_sleeve_key === parentKey);
}

function addSecurity(): void {
  allowedSecurities.value.push({
    ticker: '',
    sleeve_key: '',
    sub_sleeve_key: null,
    replacement_set_id: '',
    priority: allowedSecurities.value.length,
    enabled: true,
    exposure_suitability: null,
  });
}

function removeSecurity(index: number): void {
  allowedSecurities.value.splice(index, 1);
}

function securitySiblingTargetIndex(index: number, direction: -1 | 1): number | null {
  const security = allowedSecurities.value[index];
  if (!security) return null;
  const siblings = allowedSecurities.value
    .map((candidate, candidateIndex) => ({ candidate, candidateIndex }))
    .filter(
      ({ candidate }) =>
        candidate.sleeve_key === security.sleeve_key &&
        candidate.replacement_set_id === security.replacement_set_id,
    );
  const siblingPosition = siblings.findIndex(({ candidateIndex }) => candidateIndex === index);
  return siblings[siblingPosition + direction]?.candidateIndex ?? null;
}

function canMoveSecurity(index: number, direction: -1 | 1): boolean {
  return securitySiblingTargetIndex(index, direction) !== null;
}

function moveSecurity(index: number, direction: -1 | 1): void {
  const targetIndex = securitySiblingTargetIndex(index, direction);
  if (targetIndex === null) return;
  const current = allowedSecurities.value[index]!;
  const next = allowedSecurities.value[targetIndex]!;
  [allowedSecurities.value[index], allowedSecurities.value[targetIndex]] = [next, current];
  const oldPriority = current.priority ?? 0;
  current.priority = next.priority ?? 0;
  next.priority = oldPriority;
}

function currentOverrideTargetIsDisabled(ticker: string): boolean {
  const value = overrideTarget(ticker);
  return !!value && !enabledSleeves.value.some((sleeve) => sleeve.sleeve_key === value);
}

function overrideTarget(ticker: string): string {
  const override = overrides.value.find((item) => item.ticker === ticker);
  return override?.sub_sleeve_key ?? override?.sleeve_key ?? '';
}

function setOverrideTarget(ticker: string, event: Event): void {
  const targetKey = (event.target as HTMLSelectElement).value;
  const existing = overrides.value.findIndex((override) => override.ticker === ticker);
  if (!targetKey) {
    if (existing >= 0) overrides.value.splice(existing, 1);
    return;
  }
  const target = sleeves.value.find((sleeve) => sleeve.sleeve_key === targetKey);
  if (!target) return;
  const next: OverrideInput = target.parent_sleeve_key
    ? { ticker, sleeve_key: target.parent_sleeve_key, sub_sleeve_key: target.sleeve_key }
    : { ticker, sleeve_key: target.sleeve_key, sub_sleeve_key: null };
  if (existing >= 0) overrides.value[existing] = next;
  else overrides.value.push(next);
}

onMounted(() => {
  void loadInitial();
});
</script>

<style scoped>
.policy-page .page-subtitle,
.policy-page .section-subtitle {
  max-width: 58rem;
  margin-top: 0.3rem;
  font-size: 0.82rem;
}
.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
  align-items: center;
}
.primary-button,
.secondary-button,
.danger-button,
.text-button,
.icon-button {
  min-height: 2.4rem;
  padding: 0.55rem 0.85rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 750;
  cursor: pointer;
}
.primary-button {
  background: #087f7d;
  color: #fff;
}
.secondary-button {
  border-color: #bdcfd8;
  background: #fff;
  color: #29475a;
}
.danger-button {
  border-color: #e5c7c5;
  background: #fff5f4;
  color: #954541;
}
.text-button {
  background: transparent;
  color: #087f7d;
}
.icon-button {
  min-height: 1.7rem;
  padding: 0.15rem 0.45rem;
  border-color: #dce6eb;
  background: #fff;
  color: #31576c;
}
button:disabled {
  opacity: 0.52;
  cursor: not-allowed;
}
.demo-notice,
.notice-card,
.validation-card,
.success-card,
.delete-panel,
.revision-panel,
.panel,
.target-panel,
.activation-panel {
  border: 1px solid #dce6eb;
  border-radius: 0.8rem;
  background: #fff;
  box-shadow: 0 4px 20px rgb(18 55 77 / 4.5%);
}
.demo-notice {
  margin: 0;
  padding: 0.85rem 1rem;
  border-color: #f2dcad;
  background: #fff7e8;
  color: #765016;
  font-size: 0.8rem;
  line-height: 1.5;
}
.revision-panel,
.panel,
.target-panel,
.activation-panel {
  padding: clamp(1rem, 2vw, 1.3rem);
}
.section-heading {
  align-items: center;
  margin-bottom: 1rem;
}
.section-heading h2 {
  margin: 0;
  color: #10263d;
  font-size: 1.08rem;
  letter-spacing: -0.025em;
}
.revision-controls {
  display: grid;
  grid-template-columns: minmax(14rem, 1.2fr) minmax(18rem, 2fr) auto;
  gap: 0.8rem;
  align-items: end;
  min-width: 0;
}
.revision-id {
  display: grid;
  gap: 0.35rem;
  color: #637b8a;
  font-size: 0.72rem;
}
.revision-id code {
  overflow-wrap: anywhere;
  color: #29475a;
  font-size: 0.75rem;
}
.status-badge,
.demo-badge {
  display: inline-flex;
  align-items: center;
  padding: 0.35rem 0.55rem;
  border-radius: 999px;
  background: #e7f2f2;
  color: #126e6a;
  font-size: 0.68rem;
  font-weight: 800;
  white-space: nowrap;
}
.status-warning {
  background: #fff1d7;
  color: #805916;
}
.status-ready {
  background: #e7f2f2;
  color: #126e6a;
}
.state-message,
.success-message,
.empty-note {
  margin: 0.8rem 0 0;
  color: #657d8b;
  font-size: 0.78rem;
  line-height: 1.5;
}
.success-message {
  color: #137a60;
}
.notice-card,
.delete-panel {
  display: grid;
  gap: 0.7rem;
  margin-top: 0.8rem;
  padding: 0.9rem;
  border-color: #f2dcad;
  background: #fffaf0;
}
.notice-card p,
.delete-panel p {
  margin: 0;
  color: #735019;
  font-size: 0.78rem;
  line-height: 1.5;
}
.validation-card,
.success-card {
  margin: 0.8rem 0;
  padding: 0.8rem 1rem;
  font-size: 0.78rem;
  line-height: 1.5;
}
.validation-card {
  border-color: #f2dcad;
  background: #fffaf0;
  color: #765016;
}
.validation-card ul,
.backend-errors,
.form-issues {
  margin: 0.45rem 0;
  padding-left: 1.25rem;
}
.validation-card p {
  margin: 0.35rem 0 0;
}
.success-card {
  border-color: #c8e5dc;
  background: #f1faf6;
  color: #17634e;
}
.table-scroll {
  min-width: 0;
  overflow-x: auto;
  border: 1px solid #e6edf1;
  border-radius: 0.65rem;
}
.editor-table {
  width: 100%;
  min-width: 1020px;
  border-collapse: collapse;
  text-align: left;
  font-size: 0.72rem;
}
.editor-table th {
  padding: 0.65rem 0.55rem;
  background: #f5f8fa;
  color: #536d7c;
  font-size: 0.66rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.editor-table td {
  min-width: 6rem;
  padding: 0.55rem;
  border-top: 1px solid #edf2f4;
  vertical-align: top;
}
.editor-table tr:focus-within {
  background: #f8fcfc;
}
.disabled-row {
  background: #f6f7f8;
  color: #7d8d96;
}
.order-tools {
  display: flex;
  gap: 0.25rem;
  margin-bottom: 0.35rem;
}
.compact-field,
.field {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
  color: #466779;
  font-size: 0.7rem;
  font-weight: 700;
}
.compact-field input,
.compact-field select,
.field input,
.field select {
  width: 100%;
  min-width: 0;
  min-height: 2.15rem;
  padding: 0.45rem 0.55rem;
  border: 1px solid #cbd9e0;
  border-radius: 0.4rem;
  background: #fff;
  color: #29475a;
  font: inherit;
  font-size: 0.76rem;
}
.compact-field input:focus,
.compact-field select:focus,
.field select:focus {
  border-color: #087f7d;
  outline: 2px solid rgb(8 127 125 / 18%);
}
.target-input {
  min-width: 5rem;
}
.priority-input {
  min-width: 4.5rem;
}
.designation-cell {
  min-width: 12rem !important;
}
.designation-cell label,
.toggle-field {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin: 0.1rem 0;
  color: #526c7c;
  font-size: 0.68rem;
  font-weight: 600;
}
.designation-cell input,
.toggle-field input {
  accent-color: #087f7d;
}
.toggle-field {
  margin: 0.2rem 0;
}
.reassignment-field {
  min-width: 10rem;
  margin-top: 0.45rem;
}
.reassignment-field span {
  color: #8b5d20;
  font-size: 0.66rem;
}
.empty-cell {
  padding: 1.2rem !important;
  color: #718691;
  text-align: center;
}
.small-button {
  min-height: 1.9rem;
  padding: 0.35rem 0.55rem;
  font-size: 0.68rem;
}
.delete-panel h3 {
  margin: 0;
  color: #10263d;
  font-size: 0.9rem;
}
.reparent-row {
  max-width: 30rem;
}
.inline-error {
  color: #9b4242 !important;
  font-weight: 700;
}
.field-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.8rem;
}
.settings-group {
  padding: 1rem 0;
  border-top: 1px solid #e6edf1;
}
.settings-group:first-of-type {
  border-top: 0;
}
.settings-group h3 {
  margin: 0 0 0.65rem;
  color: #29475a;
  font-size: 0.86rem;
}
.unit-note {
  margin: 0 0 0.8rem;
  color: #718691;
  font-size: 0.72rem;
  line-height: 1.5;
}
.toggle-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.8rem;
  margin-top: 0.9rem;
}
.form-issues {
  padding: 0.75rem 1rem 0.75rem 2rem;
  border: 1px solid #e9c4c2;
  border-radius: 0.6rem;
  background: #fff6f5;
  color: #8f4642;
  font-size: 0.74rem;
  line-height: 1.55;
}
.api-errors-label {
  margin: 0.8rem 0 0.35rem;
  color: #855319;
  font-size: 0.76rem;
  font-weight: 800;
}
.backend-errors {
  color: #855319;
  font-size: 0.74rem;
  line-height: 1.5;
}
.capability-note {
  margin: 0.9rem 0 0;
  padding-top: 0.8rem;
  border-top: 1px solid #e6edf1;
  color: #718691;
  font-size: 0.72rem;
  line-height: 1.55;
}
.error-stack {
  display: grid;
  gap: 0.5rem;
}
.sr-only {
  position: absolute;
  left: 0;
  top: 0;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
  border: 0;
}
@media (max-width: 1050px) {
  .field-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .revision-controls {
    grid-template-columns: 1fr 1fr;
  }
  .revision-controls .text-button {
    justify-self: start;
  }
}
@media (max-width: 700px) {
  .page-header,
  .section-heading {
    flex-direction: column;
    align-items: stretch;
  }
  .page-actions {
    justify-content: flex-start;
  }
  .page-actions button {
    flex: 1 1 auto;
  }
  .revision-controls,
  .field-grid,
  .toggle-grid {
    grid-template-columns: 1fr;
  }
}
</style>
