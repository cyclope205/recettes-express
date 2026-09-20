/* Carte Lovelace pour l'integration Recettes Express.
 * A copier dans config/custom_components/recettes_express/www/recettes-express-card.js
 * (servie et enregistree automatiquement par l'integration, aucune ressource
 * a ajouter manuellement).
 *
 * Configuration de la carte (YAML ou UI) :
 *   type: custom:recettes-express-card
 *   entity_stock: sensor.aliments
 *   entity_expiring: sensor.bientot_perime
 */

const CATEGORY_LABELS = {
  fruits_legumes: "🍎 Fruits & légumes",
  viandes_poissons: "🥩 Viandes & poissons",
  produits_laitiers: "🥛 Produits laitiers",
  surgeles: "🧊 Surgelés",
  pain_boulangerie: "🥖 Pain & boulangerie",
  condiments_epices: "🧂 Condiments & épices",
  boissons: "🥤 Boissons",
  epicerie: "🥫 Épicerie",
  autres: "📦 Autres",
};
const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS);

class RecettesExpressCard extends HTMLElement {
  setConfig(config) {
    this._config = {
      entity_stock: "sensor.aliments",
      entity_expiring: "sensor.bientot_perime",
      ...config,
    };
    this._pendingItems = [];
    this._recipes = [];
    this._loading = null;
    this._error = null;
    this._recording = false;
    this._manualItem = { name: "", quantity: 1, unit: "piece", expiration_date: "" };
    this._manualOpen = false;
    this._stockOpen = true;
    this._selectedItemIds = new Set();
    this._capturingPhoto = false;
    this._stockFilter = "";
    this._stockSort = "expiration";
    this._editingItemId = null;
    this._editItem = { name: "", quantity: 1, unit: "piece", expiration_date: "" };
    this._recipeOptions = { servings: "", vegetarian: false, max_prep_minutes: "" };
    this._recipeOptionsOpen = false;
    this._render();
  }

  connectedCallback() {
    this._onVisibilityChange = () => {
      if (document.visibilityState === "visible" && this._config) {
        this._capturingPhoto = false;
        this._render();
      }
    };
    document.addEventListener("visibilitychange", this._onVisibilityChange);
  }

  disconnectedCallback() {
    if (this._onVisibilityChange) {
      document.removeEventListener("visibilitychange", this._onVisibilityChange);
    }
  }

  set hass(hass) {
    this._hass = hass;
    if (this._capturingPhoto) {
      return;
    }
    const snapshot = this._computeStateSnapshot(hass);
    if (snapshot === this._lastStateSnapshot) {
      return;
    }
    this._lastStateSnapshot = snapshot;
    this._render();
  }

  _computeStateSnapshot(hass) {
    const ids = [this._config.entity_stock, this._config.entity_expiring];
    return ids
      .map((id) => {
        const state = hass.states[id];
        return state ? `${id}:${state.state}:${JSON.stringify(state.attributes.items || [])}` : `${id}:missing`;
      })
      .join("|");
  }

  getCardSize() {
    // Estimation dynamique plutot qu'une constante fixe : une carte dont
    // la taille annoncee a Lovelace colle a son contenu reel aide le
    // moteur de mise en page (masonry/sections) a lui reserver la bonne
    // place des le depart, plutot que de decouvrir un desaccord de
    // hauteur apres coup.
    let size = 4; // en-tete + section stock + barre d'actions
    if (this._pendingItems.length > 0) size += 1 + this._pendingItems.length;
    if (this._recipes.length > 0) size += 1 + this._recipes.length * 2;
    if (this._manualOpen) size += 2;
    if (this._recipeOptionsOpen) size += 1;
    return size;
  }

  static getStubConfig() {
    return {
      entity_stock: "sensor.aliments",
      entity_expiring: "sensor.bientot_perime",
    };
  }

  _setError(message) {
    this._error = message;
    this._render();
  }

  async _callService(service, data, expectResponse = false) {
    return this._hass.connection.sendMessagePromise({
      type: "call_service",
      domain: "recettes_express",
      service,
      service_data: data,
      return_response: expectResponse,
    });
  }

  _fileToBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsDataURL(file);
    });
  }

  // Les photos prises par l'appareil photo natif font souvent plusieurs
  // Mo en pleine resolution (8-12+ Mpx) - inutile pour identifier un
  // aliment, et c'est l'essentiel du delai observe : upload + traitement
  // cote Gemini d'une image bien plus grande que necessaire. On la
  // redimensionne et recompresse cote carte avant l'envoi (1024px de
  // cote max, JPEG qualite 0.8) : suffisant pour lire un nom/une DLC,
  // et generalement 10-20x plus leger, donc bien plus rapide de bout
  // en bout. En cas d'echec (format non supporte par le canvas, etc.),
  // on retombe sur l'image d'origine plutot que de bloquer l'ajout.
  async _fileToCompressedBase64(file, maxSize = 900) {
    try {
      const original = await this._fileToBase64(file);
      const img = await new Promise((resolve, reject) => {
        const image = new Image();
        image.onload = () => resolve(image);
        image.onerror = reject;
        image.src = original;
      });
      const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      const ctx = canvas.getContext("2d");
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

      // Compression adaptative : une premiere passe a qualite raisonnable
      // (0.7) suffit dans la grande majorite des cas, mais une photo tres
      // detaillee (beaucoup de texture/texte) peut rester lourde meme
      // apres redimensionnement. On resserre alors la qualite par paliers
      // jusqu'a repasser sous un seuil raisonnable, plutot que d'envoyer
      // tel quel un fichier qui ralentirait l'upload et l'analyse.
      const MAX_BASE64_LENGTH = 350000; // ~260 Ko decodes
      let quality = 0.7;
      let dataUrl = canvas.toDataURL("image/jpeg", quality);
      for (let i = 0; i < 3 && dataUrl.length > MAX_BASE64_LENGTH && quality > 0.3; i++) {
        quality -= 0.15;
        dataUrl = canvas.toDataURL("image/jpeg", quality);
      }

      // Si l'image d'origine etait deja plus petite/legere que ce qu'on
      // vient de produire (petite photo deja bien compressee), pas la
      // peine de la degrader pour rien.
      return dataUrl.length < original.length ? dataUrl : original;
    } catch {
      return this._fileToBase64(file);
    }
  }

  _daysUntil(dateStr) {
    if (!dateStr) return null;
    const diff = (new Date(dateStr) - new Date(new Date().toDateString())) / 86400000;
    return Math.round(diff);
  }

  _addDaysISO(days) {
    const d = new Date();
    d.setDate(d.getDate() + Number(days));
    return d.toISOString().slice(0, 10);
  }

  _expiryBadgeClass(dateStr) {
    const days = this._daysUntil(dateStr);
    if (days === null) return "";
    if (days <= 1) return "badge-critical";
    if (days <= 3) return "badge-warning";
    return "badge-ok";
  }

  _recipeEmoji(title) {
    const t = (title || "").toLowerCase();
    const rules = [
      [/soupe|velout|potage|bouillon|gaspacho/, "🥣"],
      [/salade/, "🥗"],
      [/p[âa]tes|spaghetti|nouilles|lasagne|macaroni/, "🍝"],
      [/pizza/, "🍕"],
      [/gratin|fromage|quiche/, "🧀"],
      [/poulet|volaille|dinde|canard/, "🍗"],
      [/poisson|saumon|thon|crevette|fruits de mer/, "🐟"],
      [/riz|risotto/, "🍚"],
      [/tarte|g[âa]teau|dessert|crumble|cookie|brownie/, "🍰"],
      [/curry|wok/, "🍛"],
      [/omelette|oeuf|œuf/, "🍳"],
      [/sandwich|burger|wrap|panini/, "🥪"],
      [/l[ée]gume|ratatouille|po[êe]l[ée]e/, "🥕"],
      [/pain|toast|tartine/, "🍞"],
      [/crepe|cr[êe]pe|pancake|galette/, "🥞"],
    ];
    for (const [regex, emoji] of rules) {
      if (regex.test(t)) return emoji;
    }
    return "🍽️";
  }

  _describeError(err) {
    if (!err) return "erreur inconnue";
    if (typeof err === "string") return err;
    if (err.message) return err.message;
    if (err.code && err.message) return `${err.code}: ${err.message}`;
    try {
      return JSON.stringify(err);
    } catch {
      return String(err);
    }
  }

  async _onPhotoSelected(ev) {
    this._capturingPhoto = false;
    // On garde une reference stable vers le champ AVANT le premier await.
    // Cause exacte du bug : sur l'app companion, `ev.target` peut devenir
    // null une fois l'evenement considere "traite" par le moteur du
    // WebView, ce qui arrive precisement pendant les await qui suivent
    // (conversion du fichier + appel reseau). `ev.target.value = ""`
    // dans le bloc finally levait alors une exception AVANT d'atteindre
    // le render() juste apres, qui n'etait donc jamais execute - d'ou
    // le resultat jamais affiche tant qu'un clic ailleurs (ex. ouvrir le
    // formulaire manuel) ne declenchait pas un rendu par un autre chemin.
    const inputEl = ev.target;
    const file = inputEl.files && inputEl.files[0];
    if (!file) {
      return;
    }

    try {
      this._error = null;
      this._loading = "photo";
      this._render();

      const base64 = await this._fileToCompressedBase64(file);
      const result = await this._callService(
        "add_item_from_photo",
        { image_base64: base64 },
        true
      );
      const items = (result && result.response && result.response.detected_items) || [];
      if (items.length === 0) {
        this._error = "Aucun aliment detecte sur cette photo.";
      }
      const detectedItems = items.map((item) => ({
        name: item.name || "",
        quantity: item.quantity ?? 1,
        unit: item.unit || "piece",
        expiration_date: item.expiration_date || "",
      }));
      this._pendingItems = this._pendingItems.concat(detectedItems);
    } catch (err) {
      this._error = "Erreur reconnaissance photo : " + this._describeError(err);
    } finally {
      this._loading = null;
      // inputEl (capture avant les await) plutot que ev.target : voir
      // le commentaire au debut de la fonction. On protege quand meme
      // par un try/catch au cas ou l'element ait carrement ete retire
      // du DOM entre-temps (le champ est de toute facon recree a
      // l'identique au prochain rendu, cette ligne n'est qu'un nettoyage).
      try {
        inputEl.value = "";
      } catch {
        // sans consequence si ca echoue malgre tout
      }
      this._render();
    }
  }

  async _onVoiceClick() {
    if (this._recording) {
      if (this._mediaRecorder && this._mediaRecorder.state !== "inactive") {
        this._mediaRecorder.stop();
      }
      return;
    }
    if (this._loading) {
      return;
    }
    this._error = null;
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this._error =
        "Le micro necessite une connexion securisee (HTTPS) a Home Assistant. " +
        "Sur une IP locale en http:// (y compris via Tailscale sans certificat), les navigateurs bloquent l'acces au micro " +
        "(meme limitation que l'Assist officiel de Home Assistant). Utilisez un acces HTTPS (Nabu Casa, certificat local, " +
        "reverse proxy...) pour activer cette fonctionnalite.";
      this._render();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = ["audio/webm", "audio/mp4", "audio/ogg"].find(
        (type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)
      );
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      const chunks = [];
      recorder.addEventListener("dataavailable", (e) => {
        if (e.data && e.data.size > 0) {
          chunks.push(e.data);
        }
      });
      recorder.addEventListener("stop", () => {
        stream.getTracks().forEach((track) => track.stop());
        this._recording = false;
        const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
        this._onVoiceRecorded(blob);
      });
      this._mediaRecorder = recorder;
      recorder.start();
      this._recording = true;
      this._render();
    } catch (err) {
      this._recording = false;
      this._error = "Microphone indisponible : " + this._describeError(err);
      this._render();
    }
  }

  async _onVoiceRecorded(blob) {
    if (!blob || blob.size === 0) {
      this._error = "Aucun son enregistre.";
      this._render();
      return;
    }

    try {
      this._error = null;
      this._loading = "voice";
      this._render();

      const dataUrl = await this._fileToBase64(blob);
      const base64 = String(dataUrl).split(",")[1] || dataUrl;
      const result = await this._callService(
        "add_item_from_voice",
        { audio_base64: base64, audio_mime_type: blob.type || "audio/webm" },
        true
      );
      const items = (result && result.response && result.response.detected_items) || [];
      if (items.length === 0) {
        this._error = "Aucun aliment detecte dans cet enregistrement.";
      }
      const detectedItems = items.map((item) => ({
        name: item.name || "",
        quantity: item.quantity ?? 1,
        unit: item.unit || "piece",
        expiration_date: item.expiration_date || "",
      }));
      this._pendingItems = this._pendingItems.concat(detectedItems);
    } catch (err) {
      this._error = "Erreur reconnaissance micro : " + this._describeError(err);
    } finally {
      this._loading = null;
      this._render();
    }
  }

  async _confirmPendingItem(index) {
    const item = this._pendingItems[index];
    if (!item.name || !item.name.trim()) {
      this._setError("Le nom de l'aliment est vide.");
      return;
    }
    if (!item.expiration_date) {
      this._setError("La date de peremption est obligatoire pour ajouter cet aliment.");
      return;
    }
    try {
      await this._callService("add_item", {
        name: item.name.trim(),
        quantity: parseFloat(item.quantity) || 1,
        unit: item.unit,
        expiration_date: item.expiration_date,
      });
      this._pendingItems.splice(index, 1);
      this._error = null;
      this._render();
    } catch (err) {
      this._setError("Erreur ajout au stock : " + this._describeError(err));
    }
  }

  _discardPendingItem(index) {
    this._pendingItems.splice(index, 1);
    this._render();
  }

  _updatePendingField(index, field, value) {
    this._pendingItems[index][field] = value;
  }

  async _removeItem(itemId, itemName) {
    if (!confirm(`Retirer "${itemName}" du stock ?`)) return;
    try {
      await this._callService("remove_item", { item_id: itemId });
      this._selectedItemIds.delete(itemId);
      this._error = null;
      this._render();
    } catch (err) {
      this._setError("Erreur suppression : " + this._describeError(err));
    }
  }

  _toggleItemSelected(itemId) {
    if (this._selectedItemIds.has(itemId)) {
      this._selectedItemIds.delete(itemId);
    } else {
      this._selectedItemIds.add(itemId);
    }
    this._render();
  }

  _setSelection(items, select) {
    items.forEach((item) => {
      if (select) this._selectedItemIds.add(item.id);
      else this._selectedItemIds.delete(item.id);
    });
    this._render();
  }

  _selectExpiringItems() {
    const expiring = (this._hass && this._getEntityItems(this._config.entity_expiring)) || [];
    expiring.forEach((item) => this._selectedItemIds.add(item.id));
    this._render();
  }

  _clearSelection() {
    this._selectedItemIds.clear();
    this._render();
  }

  async _suggestRecipes() {
    this._error = null;
    this._loading = "recipes";
    this._render();
    try {
      const itemIds = Array.from(this._selectedItemIds);
      const payload = { max_recipes: 3 };
      if (itemIds.length > 0) payload.item_ids = itemIds;
      const servings = parseInt(this._recipeOptions.servings, 10);
      if (servings > 0) payload.servings = servings;
      if (this._recipeOptions.vegetarian) payload.vegetarian = true;
      const maxPrepMinutes = parseInt(this._recipeOptions.max_prep_minutes, 10);
      if (maxPrepMinutes > 0) payload.max_prep_minutes = maxPrepMinutes;
      const result = await this._callService("suggest_recipes", payload, true);
      this._recipes = (result && result.response && result.response.recipes) || [];
      if (this._recipes.length === 0) {
        this._error = "Aucune recette proposee (stock insuffisant ?).";
      }
    } catch (err) {
      this._setError("Erreur suggestion de recettes : " + this._describeError(err));
    } finally {
      this._loading = null;
      this._render();
    }
  }

  async _acceptRecipe(index) {
    const recipe = this._recipes[index];
    if (!confirm(`Valider "${recipe.title}" et retirer les ingredients du stock ?`)) return;
    try {
      const result = await this._callService(
        "accept_recipe",
        { recipe_index: index },
        true
      );
      const removedCount = (result && result.response && result.response.removed_count) || 0;
      recipe._accepted = true;
      recipe._removedCount = removedCount;
      this._recipes = this._recipes.filter((r) => r === recipe);
      this._selectedItemIds.clear();
      this._error = null;
      this._render();
      if (removedCount === 0) {
        this._setError(
          "Recette validee, mais aucun ingredient n'a pu etre retire du stock " +
            "(ont-ils deja ete supprimes entre-temps ?)."
        );
      }
    } catch (err) {
      this._setError("Erreur validation recette : " + this._describeError(err));
    }
  }

  _finishRecipe(index) {
    this._recipes.splice(index, 1);
    this._render();
  }

  _dismissRecipe(index) {
    this._recipes.splice(index, 1);
    this._render();
  }

  _toggleStockSection() {
    this._stockOpen = !this._stockOpen;
    this._render();
  }

  _toggleManualForm() {
    this._manualOpen = !this._manualOpen;
    this._render();
  }

  _toggleRecipeOptions() {
    this._recipeOptionsOpen = !this._recipeOptionsOpen;
    this._render();
  }

  _renderRecipeOptions() {
    const opts = this._recipeOptions;
    return `
      <div class="recipe-options ${this._recipeOptionsOpen ? "" : "collapsed"}">
        <div class="recipe-options-row">
          <label class="recipe-options-field">
            <span>👥 Personnes</span>
            <input type="number" min="1" max="20" step="1" id="recipe-servings" placeholder="—" value="${this._escapeHtml(opts.servings)}" />
          </label>
          <label class="recipe-options-field">
            <span>⏱️ Temps max (min)</span>
            <input type="number" min="5" max="240" step="5" id="recipe-max-time" placeholder="—" value="${this._escapeHtml(opts.max_prep_minutes)}" />
          </label>
        </div>
        <label class="recipe-options-checkbox">
          <input type="checkbox" id="recipe-vegetarian" ${opts.vegetarian ? "checked" : ""} />
          <span>🥦 Vegetarien uniquement</span>
        </label>
      </div>`;
  }

  _updateManualField(field, value) {
    this._manualItem[field] = value;
  }

  async _submitManualItem() {
    const item = this._manualItem;
    if (!item.name || !item.name.trim()) {
      this._setError("Le nom de l'aliment est vide.");
      return;
    }
    if (!item.expiration_date) {
      this._setError("La date de peremption est obligatoire.");
      return;
    }
    try {
      await this._callService("add_item", {
        name: item.name.trim(),
        quantity: parseFloat(item.quantity) || 1,
        unit: item.unit,
        expiration_date: item.expiration_date,
      });
      this._manualItem = { name: "", quantity: 1, unit: "piece", expiration_date: "" };
      this._error = null;
      this._render();
    } catch (err) {
      this._setError("Erreur ajout au stock : " + this._describeError(err));
    }
  }

  _escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  _filterAndSortStockItems(items) {
    let result = items;
    if (this._stockFilter && this._stockFilter.trim()) {
      const q = this._stockFilter.trim().toLowerCase();
      result = result.filter((item) => item.name.toLowerCase().includes(q));
    }
    result = result.slice();
    if (this._stockSort === "name") {
      result.sort((a, b) => a.name.localeCompare(b.name));
    } else {
      result.sort((a, b) => (a.expiration_date || "9999-99-99").localeCompare(b.expiration_date || "9999-99-99"));
    }
      if (this._selectedItemIds && this._selectedItemIds.size) {
    const checked = [];
    const unchecked = [];
    result.forEach((item) => {
      (this._selectedItemIds.has(item.id) ? checked : unchecked).push(item);
    });
    result = checked.concat(unchecked);
  }
return result;
  }

  _startEditItem(item) {
    this._editingItemId = item.id;
    this._editItem = {
      name: item.name,
      quantity: item.quantity,
      unit: item.unit,
      expiration_date: item.expiration_date || "",
    };
    this._render();
  }

  _cancelEditItem() {
    this._editingItemId = null;
    this._render();
  }

  _updateEditField(field, value) {
    this._editItem[field] = value;
  }

  async _saveEditItem() {
    const edit = this._editItem;
    if (!edit.name || !edit.name.trim()) {
      this._setError("Le nom de l'aliment est vide.");
      return;
    }
    if (!edit.expiration_date) {
      this._setError("La date de peremption est obligatoire.");
      return;
    }
    try {
      await this._callService("update_item", {
        item_id: this._editingItemId,
        name: edit.name.trim(),
        quantity: parseFloat(edit.quantity) || 1,
        unit: edit.unit,
        expiration_date: edit.expiration_date,
      });
      this._editingItemId = null;
      this._error = null;
      this._render();
    } catch (err) {
      this._setError("Erreur modification : " + this._describeError(err));
    }
  }

  _renderStockEditRow(item) {
    const edit = this._editItem;
    return `
    <div class="pending-row stock-edit-row">
      <input type="text" class="edit-name" value="${this._escapeHtml(edit.name)}" placeholder="Nom de l'aliment" />
      <div class="pending-row-line2">
        <input type="number" step="0.1" class="edit-qty" value="${this._escapeHtml(edit.quantity)}" />
        <select class="edit-unit">
          ${["g", "kg", "cl", "l", "piece", "boite", "paquet"]
            .map((u) => `<option value="${u}" ${u === edit.unit ? "selected" : ""}>${u}</option>`)
            .join("")}
        </select>
        <input type="date" class="edit-exp" value="${edit.expiration_date}" required />
        <div class="pending-actions">
          <button class="confirm-btn" id="save-edit-btn" title="Enregistrer">✓</button>
          <button class="discard-btn" id="cancel-edit-btn" title="Annuler">✕</button>
        </div>
      </div>
    </div>`;
  }

    _getEntityItems(entityId) {
    const state = this._hass && this._hass.states[entityId];
    if (!state) return null;
    return state.attributes.items || [];
  }

  _renderStockSection(items) {
    if (items === null) {
      return `
        <div class="stock-card">
          <div class="stock-card-header">
            <span class="stock-icon">🧺</span>
            <span class="stock-title">Aliments</span>
          </div>
          <p class="empty-hint">Entite introuvable — verifiez la config de la carte (entity_stock).</p>
        </div>`;
    }
    const open = this._stockOpen;
    const allSelected = items.length > 0 && items.every((item) => this._selectedItemIds.has(item.id));
    const displayItems = this._filterAndSortStockItems(items);
    const renderItemRow = (item) =>
      this._editingItemId === item.id
        ? this._renderStockEditRow(item)
        : `
    <div class="stock-row">
    <input
    type="checkbox"
    class="item-select-checkbox"
    data-item-id="${item.id}"
    ${this._selectedItemIds.has(item.id) ? "checked" : ""}
    title="Selectionner pour une suggestion de recette"
    />
    <div class="stock-row-main">
    <span class="stock-name">${this._escapeHtml(item.name)}</span>
    <span class="stock-qty">${this._escapeHtml(item.quantity)} ${this._escapeHtml(item.unit)}</span>
    </div>
    <div class="stock-row-side">
    ${
    item.expiration_date
    ? `<span class="badge ${this._expiryBadgeClass(item.expiration_date)}">${item.expiration_date}</span>`
    : ""
    }
    <button class="icon-btn edit-item-btn" data-item-id="${item.id}" title="Modifier">✏️</button>
    <button class="icon-btn remove-item-btn" data-item-id="${item.id}" data-item-name="${this._escapeHtml(item.name)}" title="Retirer">✕</button>
    </div>
    </div>`;
    const selectedItems = displayItems.filter((item) => this._selectedItemIds.has(item.id));
    const unselectedItems = displayItems.filter((item) => !this._selectedItemIds.has(item.id));
    const selectedSection =
      selectedItems.length === 0
        ? ""
        : `<div class="category-header selected-header">✅ Aliments selectionnes <span class="category-count">${selectedItems.length}</span></div>` + selectedItems.map(renderItemRow).join("");
    const rows =
      displayItems.length === 0
        ? `<p class="empty-hint">${this._stockFilter ? "Aucun aliment ne correspond a la recherche." : "Rien ici pour le moment, ajoutez un aliment par photo ou manuellement ci-dessous."}</p>`
        : selectedSection + CATEGORY_ORDER
            .map((cat) => {
              const group = unselectedItems.filter((item) => (item.category || "autres") === cat);
              if (group.length === 0) return "";
              const label = CATEGORY_LABELS[cat] || cat;
              return `<div class="category-header">${label} <span class="category-count">${group.length}</span></div>` + group.map(renderItemRow).join("");
            })
            .join("");

    return `
      <div class="stock-card">
        <div class="stock-card-header">
          <button class="stock-card-toggle" id="stock-toggle">
            <span class="stock-icon">🧺</span>
            <span class="stock-title">Aliments</span>
            <span class="stock-count">${items.length}</span>
            <span class="chevron ${open ? "open" : ""}">⌄</span>
          </button>
          ${
            items.length > 0
              ? `<button class="select-all-btn" id="select-all-btn" data-select-all="${allSelected ? "0" : "1"}">${allSelected ? "Aucun" : "Tout"}</button>`
              : ""
          }
        </div>
        ${
        items.length > 0
          ? `<div class="stock-toolbar">
        <input type="text" class="stock-filter-input" id="stock-filter-input" placeholder="Rechercher..." value="${this._stockFilter}" />
        <button class="sort-toggle-btn" id="sort-toggle-btn" title="Changer le tri">${this._stockSort === "name" ? "🔤 A-Z" : "📅 DLC"}</button>
        </div>`
          : ""
        }
        <div class="stock-card-body ${open ? "" : "collapsed"}">${rows}</div>
      </div>`;
  }

  _renderManualForm() {
    const item = this._manualItem;
    return `
      <div class="section manual-section">
        <button class="section-toggle" id="manual-toggle">
          <span class="section-title">➕ Ajouter un aliment manuellement</span>
          <span class="chevron ${this._manualOpen ? "open" : ""}">⌄</span>
        </button>
        <div class="manual-form ${this._manualOpen ? "" : "collapsed"}">
          <input type="text" id="manual-name" placeholder="Nom de l'aliment" value="${this._escapeHtml(item.name)}" />
          <div class="manual-row">
            <input type="number" step="0.1" id="manual-qty" value="${this._escapeHtml(item.quantity)}" />
            <select id="manual-unit">
              ${["g", "kg", "cl", "l", "piece", "boite", "paquet"]
                .map((u) => `<option value="${u}" ${u === item.unit ? "selected" : ""}>${u}</option>`)
                .join("")}
            </select>
            <input type="date" id="manual-exp" value="${item.expiration_date}" required title="DLC (obligatoire)" />
            <select id="manual-quick-date" class="manual-quick-date" title="Estimer rapidement (produit frais sans date imprimee)">
              <option value="">≈ estimer…</option>
              <option value="3">+ 3 jours</option>
              <option value="7">+ 1 semaine</option>
              <option value="14">+ 2 semaines</option>
              <option value="30">+ 1 mois</option>
            </select>
          </div>
          <p class="field-hint">DLC obligatoire (anti-gaspi). Produit frais sans date imprimee ? Utilisez "≈ estimer" au lieu de deviner.</p>
          <button class="btn btn-primary manual-submit-btn" id="manual-submit-btn">Ajouter au stock</button>
        </div>
      </div>`;
  }

  _renderPendingItems() {
    if (this._pendingItems.length === 0) return "";
    const rows = this._pendingItems
      .map((item, i) => {
        const missingDate = !item.expiration_date;
        return `
        <div class="pending-row">
          <input type="text" class="pending-name" data-index="${i}" value="${this._escapeHtml(item.name)}" placeholder="Nom de l'aliment" />
          <div class="pending-row-line2">
            <input type="number" step="0.1" class="pending-qty" data-index="${i}" value="${this._escapeHtml(item.quantity)}" />
            <select class="pending-unit" data-index="${i}">
              ${["g", "kg", "cl", "l", "piece", "boite", "paquet"]
                .map((u) => `<option value="${u}" ${u === item.unit ? "selected" : ""}>${u}</option>`)
                .join("")}
            </select>
            <input
              type="date"
              class="pending-exp ${missingDate ? "field-missing" : ""}"
              data-index="${i}"
              value="${item.expiration_date}"
              required
              title="DLC (obligatoire)"
            />
            <select class="pending-quick-date" data-index="${i}" title="Estimer rapidement (produit frais sans date imprimee)">
              <option value="">≈ estimer…</option>
              <option value="3">+ 3 jours</option>
              <option value="7">+ 1 semaine</option>
              <option value="14">+ 2 semaines</option>
              <option value="30">+ 1 mois</option>
            </select>
            <div class="pending-actions">
              <button
                class="confirm-btn ${missingDate ? "confirm-btn-disabled" : ""}"
                data-index="${i}"
                title="${missingDate ? "Renseignez la DLC avant d'ajouter" : "Ajouter au stock"}"
              >✓</button>
              <button class="discard-btn" data-index="${i}" title="Ignorer">✕</button>
            </div>
          </div>
        </div>`;
      })
      .join("");
    return `
      <div class="section pending-section">
        <div class="section-title">📋 Aliments detectes — a confirmer</div>
        <p class="field-hint">Verifiez le nom. Pas de date lisible (produit frais) ? Utilisez "≈ estimer" plutot que de deviner.</p>
        ${rows}
      </div>`;
  }

  _renderExpiringBanner(expiringItems) {
    if (!expiringItems || expiringItems.length === 0) return "";
    const names = expiringItems.map((i) => i.name).join(", ");
    const n = expiringItems.length;
    return `
      <button class="expiring-banner" id="select-expiring-btn" title="Cliquer pour selectionner ces aliments">
        <span class="expiring-icon">⏰</span>
        <span class="expiring-text"><strong>${n}</strong> aliment${n > 1 ? "s" : ""} bientot perime${n > 1 ? "s" : ""} : ${names}</span>
        <span class="expiring-cta">Selectionner →</span>
      </button>`;
  }

  _renderRecipes() {
    if (this._recipes.length === 0) return "";
    const palettes = [
      ["#ff7043", "#ff3d00"],
      ["#ffb300", "#ff6f00"],
      ["#ef5350", "#c62828"],
      ["#8d6e63", "#5d4037"],
    ];
    const cards = this._recipes
      .map((recipe, i) => {
        const emoji = this._recipeEmoji(recipe.title);
        const c1 = palettes[i % palettes.length][0];
        const c2 = palettes[i % palettes.length][1];
        const steps = (recipe.steps || [])
          .map(
            (s, si) => `
          <li><span class="step-num">${si + 1}</span><span class="step-text">${this._escapeHtml(s)}</span></li>`
          )
          .join("");
        return `
        <div class="recipe-card ${recipe._accepted ? "recipe-card-done" : ""}">
          <div class="recipe-hero" style="background: linear-gradient(135deg, ${c1}, ${c2});">
            <button class="dismiss-recipe-btn" data-index="${i}" title="Ignorer cette recette" aria-label="Ignorer cette recette">&times;</button>
            <span class="recipe-hero-emoji">${emoji}</span>
            <div class="recipe-hero-text">
              <div class="recipe-title">${this._escapeHtml(recipe.title)}</div>
              ${recipe.prep_minutes ? `<span class="recipe-time">⏱️ ${recipe.prep_minutes} min</span>` : ""}
            </div>
          </div>
          <ol class="recipe-steps">${steps}
          </ol>
          ${
            recipe._accepted
              ? `<p class="recipe-done-hint">Ingredients retires du stock (${recipe._removedCount || 0}).</p>
          <button class="finish-recipe-btn" data-index="${i}">Recette terminee</button>`
              : `<button class="accept-recipe-btn" data-index="${i}">✓ Valider cette recette</button>`
          }
        </div>`;
      })
      .join("");
    return `
    <div class="section recipes-section">
      <div class="section-title">🍲 Idees recettes anti-gaspi</div>
      ${cards}
    </div>`;
  }

  _render() {
    if (!this._config) return;

    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    try {
      this._renderInner();
    } catch (err) {
      // Filet de securite : si une exception survient pendant la
      // construction du HTML (par ex. une donnee inattendue), on
      // n'abandonne plus silencieusement en laissant l'ecran fige sur
      // le rendu precedent (c'est exactement ce type de plantage
      // silencieux qui causait le bug "il faut rouvrir le formulaire
      // manuel pour voir le resultat" : une exception levee AVANT la
      // mise a jour du DOM interrompait le rendu sans rien afficher).
      // On affiche desormais l'erreur explicitement.
      console.error("recettes-express-card: erreur de rendu", err);
      this.shadowRoot.innerHTML = `
        <ha-card>
          <div style="padding:16px; color:#ff8a80;">
            <strong>Erreur d'affichage de la carte Recettes Express :</strong><br>
            ${this._describeError(err)}
          </div>
        </ha-card>`;
    }

    // Signale a Lovelace que la taille de la carte a pu changer (ajout
    // de la section "a confirmer", des recettes, etc.) - certains
    // agencements (masonry) ne recalculent la hauteur des cartes
    // voisines que sur cet evenement.
    window.dispatchEvent(new Event("resize"));
  }

  _renderInner() {
    const focusInfo = this._captureFocus();

    const stockItems = this._hass ? this._getEntityItems(this._config.entity_stock) : [];
    const expiringItems = this._hass ? this._getEntityItems(this._config.entity_expiring) : [];
    const selectedCount = this._selectedItemIds.size;
    this._lastStockItems = stockItems || [];

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        ha-card {
          position: relative;
          padding: 0;
          overflow: hidden;
          border-radius: var(--ha-card-border-radius, 28px) !important;
          background: var(--ha-card-background, linear-gradient(145deg, rgba(255,255,255,0.07), rgba(255,255,255,0.015)) var(--card-background-color));
          backdrop-filter: var(--ha-card-backdrop-filter, blur(30px) saturate(180%));
          -webkit-backdrop-filter: var(--ha-card-backdrop-filter, blur(30px) saturate(180%));
          border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, rgba(255,255,255,0.12));
          box-shadow: var(--ha-card-box-shadow, 0 10px 30px rgba(0,0,0,0.18), inset 0 1px 1px rgba(255,255,255,0.08));
          color: var(--primary-text-color);
        }
        ha-card::before {
          content: "";
          position: absolute;
          inset: 0;
          z-index: 0;
          pointer-events: none;
          background: radial-gradient(circle at 10% 0%, rgba(90,169,255,0.16), transparent 40%),
                      radial-gradient(circle at 100% 100%, rgba(255,159,67,0.10), transparent 45%);
        }
        .card-header, .card-content { position: relative; z-index: 1; }

        .card-header {
          padding: 20px 22px 10px 22px;
          display: flex;
          align-items: center;
          gap: 12px;
        }
        .card-header .emoji {
          font-size: 1.3em;
          width: 42px; height: 42px;
          display: flex; align-items: center; justify-content: center;
          border-radius: 14px;
          background: linear-gradient(135deg, rgba(90,169,255,0.25), rgba(90,169,255,0.05));
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.15);
        }
        .card-header h2 {
          margin: 0;
          font-size: 1.28em;
          font-weight: 800;
          letter-spacing: 0.2px;
        }
        .card-header .emoji { font-size: 1.5em; }
        .card-header-text { min-width: 0; }
        .card-subtitle {
          margin: 2px 0 0 0;
          font-size: 0.78em;
          font-weight: 600;
          color: var(--secondary-text-color);
          opacity: 0.85;
        }
        .card-content { padding: 10px 18px 20px 18px; }

        .error-banner {
          background: linear-gradient(135deg, rgba(244,67,54,0.16), rgba(244,67,54,0.05));
          border: 1px solid rgba(244,67,54,0.35);
          color: #ff8a80;
          padding: 11px 14px;
          border-radius: 14px;
          font-size: 0.88em;
          line-height: 1.4;
          margin-bottom: 14px;
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 8px;
          box-shadow: 0 0 16px rgba(244,67,54,0.12);
          max-height: 220px;
          overflow-y: auto;
        }
        .error-banner button {
          background: none; border: none; color: inherit; cursor: pointer;
          font-size: 1.1em; line-height: 1; opacity: 0.8; flex-shrink: 0;
        }
        .error-banner button:hover { opacity: 1; }

        .expiring-banner {
          width: 100%;
          display: flex;
          align-items: center;
          gap: 10px;
          text-align: left;
          background: linear-gradient(135deg, rgba(255,152,0,0.16), rgba(255,152,0,0.04));
          border: 1px solid rgba(255,152,0,0.30);
          color: var(--primary-text-color);
          padding: 11px 14px;
          border-radius: 14px;
          margin-bottom: 14px;
          cursor: pointer;
          font: inherit;
          box-shadow: 0 0 16px rgba(255,152,0,0.10);
          transition: filter 0.15s ease;
        }
        .expiring-banner:hover { filter: brightness(1.1); }
        .expiring-icon { font-size: 1.2em; flex-shrink: 0; }
        .expiring-text { flex: 1; font-size: 0.88em; line-height: 1.35; }
        .expiring-text strong { color: #ffb74d; }
        .expiring-cta {
          flex-shrink: 0;
          font-size: 0.78em;
          font-weight: 800;
          color: #ffb74d;
          white-space: nowrap;
        }

        .clear-selection-btn {
          display: block;
          margin: -2px 0 10px 0;
          background: none;
          border: none;
          color: var(--primary-color);
          font-size: 0.82em;
          font-weight: 700;
          cursor: pointer;
          padding: 2px 0;
        }
        .clear-selection-btn:hover { text-decoration: underline; }

        .recipe-options-toggle-btn {
          flex-shrink: 0;
          background: rgba(255,255,255,0.07);
          border: 1px solid rgba(255,255,255,0.14);
          color: var(--secondary-text-color);
          border-radius: 999px;
          width: 42px;
          height: 42px;
          font-size: 1.05em;
          cursor: pointer;
          transition: background 0.15s ease, color 0.15s ease;
        }
        .recipe-options-toggle-btn:hover { background: rgba(255,255,255,0.13); color: var(--primary-text-color); }
        .recipe-options {
          display: flex;
          flex-direction: column;
          gap: 10px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 14px;
          padding: 12px;
          margin: 10px 0 6px 0;
        }
        .recipe-options.collapsed { display: none; }
        .recipe-options-row { display: flex; gap: 8px; flex-wrap: wrap; }
        .recipe-options-field {
          flex: 1;
          min-width: 120px;
          display: flex;
          flex-direction: column;
          gap: 4px;
          font-size: 0.8em;
          color: var(--secondary-text-color);
        }
        .recipe-options-field input {
          padding: 8px 10px;
          border-radius: 10px;
          border: 1px solid rgba(255,255,255,0.14);
          background: rgba(0,0,0,0.15);
          color: var(--primary-text-color);
          font: inherit;
          box-sizing: border-box;
          color-scheme: dark;
        }
        .recipe-options-checkbox {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 0.88em;
          cursor: pointer;
        }
        .recipe-options-checkbox input {
          width: 17px; height: 17px;
          accent-color: var(--primary-color);
          cursor: pointer;
        }

        .stock-card {
          background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.01));
          border: 1px solid rgba(255,255,255,0.10);
          border-radius: 18px;
          overflow: hidden;
          margin-bottom: 16px;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 2px 8px rgba(0,0,0,0.10);
        }
        .stock-card-header {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 4px 6px 4px 14px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
        }
        .stock-card-toggle {
          flex: 1;
          min-width: 0;
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 0;
          background: none;
          border: none;
          cursor: pointer;
          font: inherit;
          color: var(--primary-text-color);
          text-align: left;
        }
        .select-all-btn {
          flex-shrink: 0;
          background: rgba(255,255,255,0.07);
          border: 1px solid rgba(255,255,255,0.12);
          color: var(--secondary-text-color);
          border-radius: 999px;
          padding: 5px 11px;
          font-size: 0.72em;
          font-weight: 700;
          cursor: pointer;
          transition: background 0.15s ease, color 0.15s ease;
        }
        .select-all-btn:hover { background: rgba(255,255,255,0.13); color: var(--primary-text-color); }
        .stock-icon {
          font-size: 1.2em;
          width: 32px; height: 32px;
          display: flex; align-items: center; justify-content: center;
          border-radius: 10px;
          background: linear-gradient(135deg, rgba(90,169,255,0.28), rgba(255,159,67,0.10));
        }
        .stock-title { font-weight: 700; flex: 1; font-size: 0.98em; }
        .stock-count {
          background: linear-gradient(135deg, var(--primary-color), rgba(255,255,255,0.15));
          color: var(--text-primary-color, #fff);
          border-radius: 999px;
          min-width: 22px;
          text-align: center;
          padding: 2px 8px;
          font-size: 0.78em;
          font-weight: 800;
          box-shadow: 0 0 10px color-mix(in srgb, var(--primary-color) 45%, transparent);
        }
        .chevron { transition: transform 0.2s ease; opacity: 0.55; flex-shrink: 0; }
        .chevron.open { transform: rotate(180deg); }

        .stock-card-body { padding: 4px 14px 12px 14px; max-height: 420px; overflow-y: auto; }
.stock-toolbar { display: flex; gap: 8px; padding: 4px 14px 8px 14px; align-items: center; }
.stock-filter-input { flex: 1; padding: 7px 10px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.14); background: rgba(255,255,255,0.05); color: var(--primary-text-color); font: inherit; font-size: 0.85em; box-sizing: border-box; }
.sort-toggle-btn { flex-shrink: 0; background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.12); color: var(--secondary-text-color); border-radius: 999px; padding: 6px 11px; font-size: 0.78em; font-weight: 700; cursor: pointer; white-space: nowrap; }
.sort-toggle-btn:hover { background: rgba(255,255,255,0.13); color: var(--primary-text-color); }
        .stock-card-body.collapsed { display: none; }

        .category-header {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 14px 0 6px;
          font-size: 0.85em;
          font-weight: 600;
          opacity: 0.75;
          text-transform: uppercase;
          letter-spacing: 0.02em;
        }
        .category-header:first-child { padding-top: 4px; }
        .selected-header { color: var(--primary-color); opacity: 1; }
        .category-count {
          font-weight: 400;
          opacity: 0.7;
        }
        .stock-row {
          display: flex;
          align-items: center;
          gap: 9px;
          padding: 10px 0;
          border-bottom: 1px solid rgba(255,255,255,0.06);
        }
        .stock-row:last-child { border-bottom: none; }
        .item-select-checkbox {
          width: 17px; height: 17px;
          flex-shrink: 0;
          accent-color: var(--primary-color);
          cursor: pointer;
        }
        .stock-row-main { display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }
        .stock-name { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .stock-qty { color: var(--secondary-text-color); font-size: 0.8em; }
        .stock-row-side { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

        .badge {
          font-size: 0.72em;
          font-weight: 700;
          padding: 3px 9px;
          border-radius: 999px;
          white-space: nowrap;
        }
        .badge-critical {
          background: rgba(244, 67, 54, 0.16); color: #ff8a80;
          box-shadow: 0 0 10px rgba(244,67,54,0.25);
        }
        .badge-warning {
          background: rgba(255, 152, 0, 0.16); color: #ffb74d;
          box-shadow: 0 0 10px rgba(255,152,0,0.20);
        }
        .badge-ok {
          background: rgba(76, 175, 80, 0.16); color: #81c995;
        }

        .icon-btn {
          background: none; border: none; cursor: pointer;
          color: var(--secondary-text-color); font-size: 0.95em; padding: 4px 7px;
          border-radius: 8px;
          transition: background 0.15s ease, color 0.15s ease;
        }
        .icon-btn:hover { color: #ff8a80; background: rgba(244, 67, 54, 0.12); }

        .empty-hint { color: var(--secondary-text-color); font-size: 0.86em; padding: 8px 0; margin: 0; opacity: 0.8; }
        .field-hint { color: var(--secondary-text-color); font-size: 0.78em; margin: 4px 0 10px 0; opacity: 0.85; }

        .actions-bar {
          display: flex;
          gap: 9px;
          flex-wrap: wrap;
          align-items: center;
          margin-bottom: 6px;
        }
        .btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 7px;
          flex: 1;
          min-width: 140px;
          border: none;
          border-radius: 999px;
          padding: 12px 18px;
          font: inherit;
          font-weight: 700;
          font-size: 0.92em;
          cursor: pointer;
          transition: transform 0.08s ease, box-shadow 0.2s ease, filter 0.15s ease;
        }
        .btn:hover { filter: brightness(1.08); }
        .btn:active { transform: scale(0.96); }
        .btn-photo {
          background: rgba(255,255,255,0.07);
          color: var(--primary-text-color);
          border: 1px solid rgba(255,255,255,0.14);
        }
        .btn-voice {
          background: rgba(255,255,255,0.07);
          color: var(--primary-text-color);
          border: 1px solid rgba(255,255,255,0.14);
        }
        .btn-voice.recording {
          background: rgba(244,67,54,0.16);
          color: #f44336;
          border: 1px solid rgba(244,67,54,0.4);
          animation: recettes-express-pulse 1.4s ease-in-out infinite;
        }
        @keyframes recettes-express-pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.55; }
        }
        .btn-primary {
          background: linear-gradient(135deg, var(--primary-color), color-mix(in srgb, var(--primary-color) 60%, #7a5cff));
          color: var(--text-primary-color, #fff);
          box-shadow: 0 4px 14px color-mix(in srgb, var(--primary-color) 45%, transparent);
        }
        .btn[disabled] { opacity: 0.6; cursor: default; }
        .spinner {
          width: 14px; height: 14px;
          border: 2px solid rgba(255,255,255,0.4);
          border-top-color: currentColor;
          border-radius: 50%;
          animation: spin 0.7s linear infinite;
          display: inline-block;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        .section {
          margin-top: 18px;
          padding-top: 16px;
          border-top: 1px dashed rgba(255,255,255,0.12);
        }
        .section-title { font-weight: 700; margin-bottom: 6px; font-size: 0.95em; }

        .section-toggle {
          width: 100%;
          display: flex;
          justify-content: space-between;
          align-items: center;
          background: none;
          border: none;
          cursor: pointer;
          font: inherit;
          color: var(--primary-text-color);
          padding: 0;
          margin-bottom: 6px;
        }
        .manual-form { padding-top: 10px; }
        .manual-form.collapsed { display: none; }
        .manual-form input, .manual-form select {
          padding: 9px 11px;
          border-radius: 12px;
          border: 1px solid rgba(255,255,255,0.14);
          background: rgba(255,255,255,0.05);
          color: var(--primary-text-color);
          font: inherit;
          box-sizing: border-box;
          color-scheme: dark;
        }
        .manual-form > input#manual-name { width: 100%; margin-bottom: 9px; }
        .manual-row { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 4px; }
        .manual-row input, .manual-row select { flex: 1; min-width: 90px; }
        .manual-row input[type="date"] { min-width: 140px; }
        .manual-quick-date { flex: 1; min-width: 110px; }
        .manual-submit-btn { width: 100%; justify-content: center; margin-top: 10px; }

        .pending-row {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-bottom: 10px;
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(255,255,255,0.08);
          padding: 10px;
          border-radius: 14px;
        }
        .pending-row > input.pending-name { width: 100%; font-weight: 600; }
        .pending-row-line2 {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          align-items: center;
        }
        .pending-row-line2 .pending-qty { flex: 0 1 60px; min-width: 55px; }
        .pending-row-line2 .pending-unit { flex: 0 1 78px; min-width: 70px; }
        .pending-row-line2 .pending-exp { flex: 1 1 130px; min-width: 125px; }
        .pending-row-line2 .pending-quick-date { flex: 1 1 110px; min-width: 105px; }
        .pending-row input, .pending-row select {
          padding: 7px 9px;
          border-radius: 10px;
          border: 1px solid rgba(255,255,255,0.14);
          background: rgba(0,0,0,0.15);
          color: var(--primary-text-color);
          font: inherit;
          box-sizing: border-box;
          color-scheme: dark;
        }
        .pending-row input.field-missing {
          border-color: rgba(255,152,0,0.55);
          box-shadow: 0 0 0 1px rgba(255,152,0,0.25);
        }
        .pending-quick-date { color: var(--secondary-text-color); font-size: 0.9em; }
        .pending-actions { display: flex; gap: 5px; margin-left: auto; }
        .confirm-btn, .discard-btn {
          border: none; border-radius: 10px; width: 34px; height: 34px;
          cursor: pointer; font-weight: 700; font-size: 1em;
          transition: transform 0.08s ease;
          flex-shrink: 0;
        }
        .confirm-btn:active, .discard-btn:active { transform: scale(0.9); }
        .confirm-btn {
          background: linear-gradient(135deg, #4caf50, #2e7d32);
          color: #fff;
          box-shadow: 0 0 10px rgba(76,175,80,0.35);
        }
        .confirm-btn.confirm-btn-disabled {
          background: rgba(255,255,255,0.08);
          color: var(--secondary-text-color);
          box-shadow: none;
          cursor: not-allowed;
        }
        .discard-btn {
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(255,255,255,0.14);
          color: var(--secondary-text-color);
        }

        .recipe-card {
        background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.01));
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 18px;
        overflow: hidden;
        margin-bottom: 14px;
        box-shadow: 0 3px 12px rgba(0,0,0,0.14);
      }
      .recipe-hero {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px;
        position: relative;
      }
      .dismiss-recipe-btn {
        position: absolute;
        top: 10px;
        right: 10px;
        width: 26px;
        height: 26px;
        border-radius: 50%;
        border: none;
        background: rgba(0,0,0,0.35);
        color: #fff;
        font-size: 18px;
        line-height: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        z-index: 2;
        padding: 0;
      }
      .dismiss-recipe-btn:hover {
        background: rgba(0,0,0,0.55);
      }
      .recipe-hero::after {
        content: "";
        position: absolute;
        inset: 0;
        background: radial-gradient(circle at 90% 0%, rgba(255,255,255,0.22), transparent 55%);
        pointer-events: none;
      }
      .recipe-hero-emoji {
        font-size: 2em;
        width: 52px; height: 52px;
        flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        background: rgba(255,255,255,0.22);
        border-radius: 16px;
        box-shadow: inset 0 1px 0 rgba(255,255,255,0.35);
      }
      .recipe-hero-text { min-width: 0; }
      .recipe-title { font-weight: 800; font-size: 1.05em; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.25); }
      .recipe-time {
        display: inline-block;
        margin-top: 3px;
        font-size: 0.74em;
        font-weight: 700;
        color: #fff;
        background: rgba(255,255,255,0.22);
        padding: 2px 9px;
        border-radius: 999px;
      }
      .recipe-steps { margin: 0; padding: 14px 16px 4px 16px; list-style: none; }
      .recipe-steps li { display: flex; gap: 10px; align-items: flex-start; margin-bottom: 10px; font-size: 0.92em; line-height: 1.4; }
      .step-num {
        flex-shrink: 0;
        width: 22px; height: 22px;
        border-radius: 50%;
        background: rgba(255,111,0,0.18);
        color: #ffb74d;
        font-weight: 800;
        font-size: 0.78em;
        display: flex; align-items: center; justify-content: center;
      }
      .step-text { padding-top: 1px; }
      .accept-recipe-btn {
        display: block;
        width: calc(100% - 32px);
        margin: 4px 16px 16px 16px;
        background: linear-gradient(135deg, #ff7043, #ff3d00);
        color: #fff;
        border: none;
        border-radius: 999px;
        padding: 10px 14px;
        cursor: pointer;
        font-weight: 700;
        font-size: 0.9em;
        box-shadow: 0 3px 12px rgba(255,87,34,0.35);
        transition: filter 0.15s ease, transform 0.08s ease;
      }
      .accept-recipe-btn:hover { filter: brightness(1.08); }
      .accept-recipe-btn:active { transform: scale(0.96); }
      .recipe-card-done { opacity: 0.85; }
      .recipe-done-hint { margin: 12px 16px 0 16px; font-size: 0.88em; font-weight: 600; color: var(--secondary-text-color); }
      .finish-recipe-btn {
        display: block;
        width: calc(100% - 32px);
        margin: 8px 16px 16px 16px;
        background: transparent;
        color: var(--secondary-text-color);
        border: 1px solid var(--divider-color, rgba(255,255,255,0.2));
        border-radius: 999px;
        padding: 10px 14px;
        cursor: pointer;
        font-weight: 700;
        font-size: 0.9em;
      }
      .finish-recipe-btn:hover { filter: brightness(1.15); }
      .finish-recipe-btn:active { transform: scale(0.96); }
      </style>
      <ha-card>
        <div class="card-header">
          <span class="emoji">👨‍🍳</span>
          <div class="card-header-text">
            <h2>Recettes Express</h2>
            <p class="card-subtitle">Anti-gaspi &amp; inspiration cuisine</p>
          </div>
        </div>
        <div class="card-content">
          <div class="actions-bar">
            <button class="btn btn-photo" id="photo-btn" ${this._loading === "photo" ? "disabled" : ""}>
              ${this._loading === "photo" ? '<span class="spinner"></span> Analyse…' : "📷 Ajouter par photo"}
            </button>
            <input type="file" id="photo-input" accept="image/*" capture="environment" style="position:absolute; width:1px; height:1px; opacity:0; overflow:hidden;" />

            <button class="btn btn-voice${this._recording ? " recording" : ""}" id="voice-btn" ${this._loading === "voice" ? "disabled" : ""}>
              ${
                this._loading === "voice"
                  ? '<span class="spinner"></span> Analyse\u2026'
                  : this._recording
                  ? "\u23F9\uFE0F Arreter"
                  : "\uD83C\uDFA4 Ajouter par micro"
              }
            </button>

            <button class="btn btn-primary" id="suggest-btn" ${this._loading === "recipes" ? "disabled" : ""}>
              ${
                this._loading === "recipes"
                  ? '<span class="spinner"></span> Recherche…'
                  : selectedCount > 0
                  ? `👨‍🍳 Suggerer (${selectedCount} selectionne${selectedCount > 1 ? "s" : ""})`
                  : "👨‍🍳 Suggerer des recettes"
              }
            </button>
            <button class="recipe-options-toggle-btn" id="recipe-options-toggle" title="Options des recettes" aria-expanded="${this._recipeOptionsOpen}">⚙️</button>
          </div>
          ${
            selectedCount > 0
              ? `<button class="clear-selection-btn" id="clear-selection-btn">Effacer la selection (${selectedCount})</button>`
              : ""
          }
          ${this._renderRecipeOptions()}

          ${this._renderPendingItems()}
          ${this._renderManualForm()}
          ${this._renderRecipes()}
          ${
            this._error
              ? `<div class="error-banner"><span>${this._error}</span><button id="dismiss-error">✕</button></div>`
              : ""
          }
          ${this._renderExpiringBanner(expiringItems)}

          ${this._renderStockSection(stockItems)}
        </div>
      </ha-card>
    `;

    this._attachListeners();
    this._restoreFocus(focusInfo);
  }

  _captureFocus() {
    const active = this.shadowRoot && this.shadowRoot.activeElement;
    if (!active || !active.id) return null;
    // IMPORTANT : selectionStart/selectionEnd ne peuvent etre lus sans
    // lever d'exception que sur certains types d'<input> (texte simple).
    // Pour les types "date" et "number" (utilises ici pour la DLC et la
    // quantite), l'app companion Home Assistant (WebView Android) leve
    // une InvalidStateError des la simple LECTURE de la propriete,
    // meme apres une verification "in" (qui ne teste que l'existence de
    // la propriete sur le prototype, pas sa lisibilite pour ce type
    // precis). C'etait la cause reelle du bug "il faut rouvrir le
    // formulaire manuel pour voir le resultat" : si un champ date/number
    // avait le focus au moment ou _render() demarrait (par exemple apres
    // etre revenu de l'appareil photo), cette lecture plantait AVANT
    // meme que le DOM soit mis a jour, gelant silencieusement l'affichage
    // sur l'etat precedent - jusqu'a ce qu'un clic sur un bouton (ouvrir
    // OU fermer le formulaire, peu importe) deplace le focus vers un
    // element sans ce probleme et debloque enfin un rendu.
    const supportsSelection = ["text", "search", "url", "tel", "password"].includes(active.type);
    let selectionStart = null;
    let selectionEnd = null;
    if (supportsSelection) {
      try {
        selectionStart = active.selectionStart;
        selectionEnd = active.selectionEnd;
      } catch {
        // par securite si un navigateur se montre capricieux malgre tout
      }
    }
    return { id: active.id, selectionStart, selectionEnd };
  }

  _restoreFocus(focusInfo) {
    if (!focusInfo) return;
    const el = this.shadowRoot.getElementById(focusInfo.id);
    if (!el) return;
    el.focus();
    if (focusInfo.selectionStart !== null && typeof el.setSelectionRange === "function") {
      try {
        el.setSelectionRange(focusInfo.selectionStart, focusInfo.selectionEnd);
      } catch {
        // certains types d'input (date, number) ne supportent pas setSelectionRange
      }
    }
  }

  _attachListeners() {
    const root = this.shadowRoot;

    const dismissBtn = root.getElementById("dismiss-error");
    if (dismissBtn) dismissBtn.addEventListener("click", () => { this._error = null; this._render(); });

    const photoInput = root.getElementById("photo-input");
    const photoBtn = root.getElementById("photo-btn");
    if (photoBtn && photoInput) {
      photoBtn.addEventListener("click", () => {
        this._capturingPhoto = true;
        photoInput.click();
      });
      photoInput.addEventListener("change", (e) => this._onPhotoSelected(e));
    }

    const voiceBtn = root.getElementById("voice-btn");
    if (voiceBtn) {
      voiceBtn.addEventListener("click", () => this._onVoiceClick());
    }

    const suggestBtn = root.getElementById("suggest-btn");
    if (suggestBtn) {
      suggestBtn.addEventListener("click", () => this._suggestRecipes());
    }

    const recipeOptionsToggle = root.getElementById("recipe-options-toggle");
    if (recipeOptionsToggle) {
      recipeOptionsToggle.addEventListener("click", () => this._toggleRecipeOptions());
    }
    const recipeServingsInput = root.getElementById("recipe-servings");
    if (recipeServingsInput) {
      recipeServingsInput.addEventListener("input", (e) => { this._recipeOptions.servings = e.target.value; });
    }
    const recipeMaxTimeInput = root.getElementById("recipe-max-time");
    if (recipeMaxTimeInput) {
      recipeMaxTimeInput.addEventListener("input", (e) => { this._recipeOptions.max_prep_minutes = e.target.value; });
    }
    const recipeVegetarianInput = root.getElementById("recipe-vegetarian");
    if (recipeVegetarianInput) {
      recipeVegetarianInput.addEventListener("change", (e) => { this._recipeOptions.vegetarian = e.target.checked; });
    }

    const stockToggle = root.getElementById("stock-toggle");
    if (stockToggle) stockToggle.addEventListener("click", () => this._toggleStockSection());

    const selectAllBtn = root.getElementById("select-all-btn");
    if (selectAllBtn) {
      selectAllBtn.addEventListener("click", (e) => {
        const select = e.currentTarget.dataset.selectAll === "1";
        this._setSelection(this._lastStockItems || [], select);
      });
    }

    const manualToggle = root.getElementById("manual-toggle");
    if (manualToggle) manualToggle.addEventListener("click", () => this._toggleManualForm());

    const manualName = root.getElementById("manual-name");
    if (manualName) manualName.addEventListener("input", (e) => this._updateManualField("name", e.target.value));
    const manualQty = root.getElementById("manual-qty");
    if (manualQty) manualQty.addEventListener("input", (e) => this._updateManualField("quantity", e.target.value));
    const manualUnit = root.getElementById("manual-unit");
    if (manualUnit) manualUnit.addEventListener("change", (e) => this._updateManualField("unit", e.target.value));
    const manualExp = root.getElementById("manual-exp");
    if (manualExp) manualExp.addEventListener("input", (e) => {
      this._updateManualField("expiration_date", e.target.value);
      clearTimeout(e.target._dlcBlurTimer);
      e.target._dlcBlurTimer = setTimeout(() => e.target.blur(), 600);
    });
    const manualQuickDate = root.getElementById("manual-quick-date");
    if (manualQuickDate) {
      manualQuickDate.addEventListener("change", (e) => {
        if (e.target.value) {
          const computed = this._addDaysISO(e.target.value);
          this._updateManualField("expiration_date", computed);
          manualExp.value = computed;
          e.target.blur();
        }
      });
    }
    const manualSubmitBtn = root.getElementById("manual-submit-btn");
    if (manualSubmitBtn) manualSubmitBtn.addEventListener("click", () => this._submitManualItem());

    root.querySelectorAll(".item-select-checkbox").forEach((el) => {
      el.addEventListener("change", (e) => this._toggleItemSelected(e.currentTarget.dataset.itemId));
    });

    const expiringBtn = root.getElementById("select-expiring-btn");
    if (expiringBtn) expiringBtn.addEventListener("click", () => this._selectExpiringItems());

    const clearSelectionBtn = root.getElementById("clear-selection-btn");
    if (clearSelectionBtn) clearSelectionBtn.addEventListener("click", () => this._clearSelection());

    root.querySelectorAll(".remove-item-btn").forEach((btn) => {
      btn.addEventListener("click", (e) =>
        this._removeItem(e.currentTarget.dataset.itemId, e.currentTarget.dataset.itemName)
      );
    });
    root.querySelectorAll(".edit-item-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const itemId = e.currentTarget.dataset.itemId;
        const item = (this._lastStockItems || []).find((i) => i.id === itemId);
        if (item) this._startEditItem(item);
      });
    });

    const editNameEl = root.querySelector(".edit-name");
    if (editNameEl) editNameEl.addEventListener("input", (e) => this._updateEditField("name", e.target.value));
    const editQtyEl = root.querySelector(".edit-qty");
    if (editQtyEl) editQtyEl.addEventListener("input", (e) => this._updateEditField("quantity", e.target.value));
    const editUnitEl = root.querySelector(".edit-unit");
    if (editUnitEl) editUnitEl.addEventListener("change", (e) => this._updateEditField("unit", e.target.value));
    const editExpEl = root.querySelector(".edit-exp");
    if (editExpEl) editExpEl.addEventListener("input", (e) => {
      this._updateEditField("expiration_date", e.target.value);
      clearTimeout(e.target._dlcBlurTimer);
      e.target._dlcBlurTimer = setTimeout(() => e.target.blur(), 600);
    });
    const saveEditBtn = root.getElementById("save-edit-btn");
    if (saveEditBtn) saveEditBtn.addEventListener("click", () => this._saveEditItem());
    const cancelEditBtn = root.getElementById("cancel-edit-btn");
    if (cancelEditBtn) cancelEditBtn.addEventListener("click", () => this._cancelEditItem());

    const stockFilterInput = root.getElementById("stock-filter-input");
    if (stockFilterInput) {
      stockFilterInput.addEventListener("input", (e) => {
        this._stockFilter = e.target.value;
        this._render();
      });
    }
    const sortToggleBtn = root.getElementById("sort-toggle-btn");
    if (sortToggleBtn) {
      sortToggleBtn.addEventListener("click", () => {
        this._stockSort = this._stockSort === "name" ? "expiration" : "name";
        this._render();
      });
    }

    root.querySelectorAll(".pending-name").forEach((el) =>
      el.addEventListener("input", (e) => this._updatePendingField(+e.target.dataset.index, "name", e.target.value))
    );
    root.querySelectorAll(".pending-qty").forEach((el) =>
      el.addEventListener("input", (e) => this._updatePendingField(+e.target.dataset.index, "quantity", e.target.value))
    );
    root.querySelectorAll(".pending-unit").forEach((el) =>
      el.addEventListener("change", (e) => this._updatePendingField(+e.target.dataset.index, "unit", e.target.value))
    );
    root.querySelectorAll(".pending-exp").forEach((el) =>
      el.addEventListener("input", (e) => {
        this._updatePendingField(+e.target.dataset.index, "expiration_date", e.target.value);
        e.target.classList.toggle("field-missing", !e.target.value);
        clearTimeout(e.target._dlcBlurTimer);
        e.target._dlcBlurTimer = setTimeout(() => e.target.blur(), 600);
      })
    );
    root.querySelectorAll(".pending-quick-date").forEach((el) =>
      el.addEventListener("change", (e) => {
        if (e.target.value) {
          const computed = this._addDaysISO(e.target.value);
          this._updatePendingField(+e.target.dataset.index, "expiration_date", computed);
          const dateEl = root.querySelector(`.pending-exp[data-index="${e.target.dataset.index}"]`);
          if (dateEl) {
            dateEl.value = computed;
            dateEl.classList.remove("field-missing");
          }
          e.target.blur();
        }
      })
    );
    root.querySelectorAll(".confirm-btn").forEach((btn) =>
      btn.addEventListener("click", (e) => this._confirmPendingItem(+e.currentTarget.dataset.index))
    );
    root.querySelectorAll(".dismiss-recipe-btn").forEach((btn) =>
      btn.addEventListener("click", (e) => this._dismissRecipe(+e.currentTarget.dataset.index))
    );
    root.querySelectorAll(".discard-btn").forEach((btn) =>
      btn.addEventListener("click", (e) => this._discardPendingItem(+e.currentTarget.dataset.index))
    );
    root.querySelectorAll(".accept-recipe-btn").forEach((btn) =>
      btn.addEventListener("click", (e) => this._acceptRecipe(+e.currentTarget.dataset.index))
    );
    root.querySelectorAll(".finish-recipe-btn").forEach((btn) =>
      btn.addEventListener("click", (e) => this._finishRecipe(+e.currentTarget.dataset.index))
    );
  }
}

customElements.define("recettes-express-card", RecettesExpressCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "recettes-express-card",
  name: "Recettes Express",
  description: "Stock d'aliments, ajout par photo et suggestions de recettes anti-gaspi.",
});
