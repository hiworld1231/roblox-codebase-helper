-- Read-only context collector. No game attributes, source writes or synchronization.
local config = __CONTEXT_CONFIG__

-- This guard precedes services, listeners, source access and network activity.
if not plugin or (config.placeId ~= nil and game.PlaceId ~= config.placeId) or config.token == "" then
    return
end

local HttpService = game:GetService("HttpService")
local RunService = game:GetService("RunService")
local ScriptEditorService = game:GetService("ScriptEditorService")
local session = HttpService:GenerateGUID(false)
local sequence = 0
local alive = true
local connected = false
local paused = false
local ids = setmetatable({}, { __mode = "k" })
local tracked = {}
local byId = {}
local versions = {}
local dirty = {}
local globalConnections = {}
local documents = {}
local enabled = config.autoConnect ~= false
local pendingAction = nil
local panel
local createPanel = __CONTEXT_PANEL__
local function ui(data) if panel then panel.update(data) end end
panel = createPanel(plugin, config, function(action)
    pendingAction = action
    ui({status="Working…",connected=connected,busy=true})
end)

local function isScript(item)
    return item:IsA("Script") or item:IsA("LocalScript") or item:IsA("ModuleScript")
end

local function relevant(item)
    return isScript(item) or item:IsA("RemoteEvent") or item:IsA("RemoteFunction")
        or item:IsA("UnreliableRemoteEvent") or item:IsA("BindableEvent") or item:IsA("BindableFunction")
end

local function present(item)
    return item == game or item:IsDescendantOf(game)
end

local function mark(item, sourceChanged)
    if sourceChanged then
        versions[item] = (versions[item] or 0) + 1
    end
    dirty[item] = true
end

local ensure
ensure = function(item)
    if not item then return nil end
    if tracked[item] then return ids[item] end
    local parentId = item ~= game and ensure(item.Parent) or nil
    local id = ids[item] or HttpService:GenerateGUID(false)
    ids[item] = id
    byId[id] = item
    versions[item] = versions[item] or 0
    local connections = {}
    tracked[item] = connections
    if item ~= game then
        table.insert(connections, item:GetPropertyChangedSignal("Name"):Connect(function() mark(item, false) end))
        table.insert(connections, item.AncestryChanged:Connect(function() mark(item, false) end))
    end
    if isScript(item) then
        table.insert(connections, item:GetPropertyChangedSignal("Source"):Connect(function() mark(item, true) end))
        if item:IsA("BaseScript") then
            table.insert(connections, item:GetPropertyChangedSignal("RunContext"):Connect(function() mark(item, false) end))
            table.insert(connections, item:GetPropertyChangedSignal("Disabled"):Connect(function() mark(item, false) end))
        end
    end
    dirty[item] = true
    return id
end

local function metadata(item)
    local row = {
        id = ids[item],
        name = item == game and "game" or item.Name,
        className = item.ClassName,
        parent = item ~= game and ids[item.Parent] or nil,
        sourceVersion = versions[item] or 0,
    }
    if item:IsA("BaseScript") then
        row.runContext = item.RunContext.Name
        row.disabled = item.Disabled
    end
    return row
end

local function post(path, payload)
    if not alive then error("Plugin unloading") end
    payload.session = session
    local response = HttpService:RequestAsync({
        Url = config.endpoint .. path,
        Method = "POST",
        Headers = { ["Content-Type"] = "application/json", Authorization = "Bearer " .. config.token },
        Body = HttpService:JSONEncode(payload),
    })
    local result = HttpService:JSONDecode(response.Body)
    if not response.Success or result.error then
        error(result.error and result.error.code or "Local context bridge unavailable")
    end
    return result
end

local function forget(item)
    for _, connection in tracked[item] or {} do connection:Disconnect() end
    byId[ids[item]] = nil
    ids[item] = nil
    tracked[item] = nil
    versions[item] = nil
end

local function snapshot()
    dirty = {}
    ensure(game)
    for _, child in game:GetChildren() do ensure(child) end
    local descendants = game:GetDescendants()
    for index, item in descendants do
        if relevant(item) then ensure(item) end
        if index % 400 == 0 then task.wait() end
    end
    local rows = {}
    for item in tracked do
        if present(item) then
            ensure(item.Parent)
            table.insert(rows, metadata(item))
        else
            forget(item)
        end
    end
    post("/snapshot/begin", { seq = sequence })
    local chunk = {}
    for _, row in rows do
        table.insert(chunk, row)
        if #chunk == 250 then
            post("/snapshot/chunk", { items = chunk })
            chunk = {}
        end
    end
    if #chunk > 0 then post("/snapshot/chunk", { items = chunk }) end
    post("/snapshot/end", { count = #rows })
end

local function flush()
    if next(dirty) == nil then return end
    local batch = dirty
    dirty = {}
    -- Discover newly introduced ancestor containers before constructing the delta.
    for item in batch do
        if present(item) then ensure(item.Parent) end
    end
    for item in dirty do batch[item] = true end
    dirty = {}
    local upserts, removed = {}, {}
    for item in batch do
        if tracked[item] then
            if present(item) then
                table.insert(upserts, metadata(item))
            else
                table.insert(removed, ids[item])
                forget(item)
            end
        end
    end
    if #upserts == 0 and #removed == 0 then return end
    sequence += 1
    post("/delta", { seq = sequence, upserts = upserts, removed = removed })
end

local collectorStarted = false
local function startCollector()
    if collectorStarted then return end
    collectorStarted = true
    table.insert(globalConnections, game.DescendantAdded:Connect(function(item)
        if relevant(item) then ensure(item) end
    end))
    table.insert(globalConnections, game.DescendantRemoving:Connect(function(item)
        if tracked[item] then mark(item, false) end
    end))
    local function documentScript(document)
        if documents[document] then return documents[document] end
        local ok, item = pcall(function() return document:GetScript() end)
        if ok and item then documents[document] = item; return item end
        return nil
    end
    
    table.insert(globalConnections, ScriptEditorService.TextDocumentDidChange:Connect(function(document)
        local item = documentScript(document)
        if item and present(item) and isScript(item) then
            ensure(item)
            mark(item, true)
        end
    end))
    -- Opening a draft or closing/discarding an editor can change edit-time text
    -- without changing the Script.Source property.
    local function editorBoundary(document)
        local item = documentScript(document)
        if item and present(item) and isScript(item) then
            ensure(item)
            mark(item, true)
        end
    end
    table.insert(globalConnections, ScriptEditorService.TextDocumentDidOpen:Connect(editorBoundary))
    table.insert(globalConnections, ScriptEditorService.TextDocumentDidClose:Connect(function(document)
        -- Under deferred signals the document can already reject GetScript().
        -- Also remember documents that were open before this plugin was loaded.
        editorBoundary(document)
        documents[document] = nil
    end))
    for _, document in ScriptEditorService:GetScriptDocuments() do
        documentScript(document)
    end
end

local function answer(command)
    flush()
    local result = { requestId = command.requestId, seq = sequence }
    if command.kind == "source" then
        local item = byId[command.id]
        if not item or not present(item) or not isScript(item) or versions[item] ~= command.version then
            result.error = "Script moved, disappeared or changed; retry at the current revision"
        else
            local version = versions[item]
            local ok, text = pcall(function() return ScriptEditorService:GetEditorSource(item) end)
            -- GetEditorSource can yield; publish intervening editor changes first.
            flush()
            result.seq = sequence
            if not ok then
                result.error = "Edit-time source is inaccessible"
            elseif not present(item) or versions[item] ~= version then
                result.error = "Source changed during read; retry"
            elseif #text > 2000000 then
                result.error = "Source exceeds the 2 MB read limit"
            else
                result.source = text
                result.version = version
            end
        end
    elseif command.kind ~= "fence" then
        result.error = "Unsupported read-only command"
    end
    post("/result", result)
end

table.insert(globalConnections, plugin.Unloading:Connect(function()
    alive = false
    if panel then panel.destroy() end
    for _, connection in globalConnections do connection:Disconnect() end
    for item in tracked do forget(item) end
    table.clear(dirty)
    table.clear(documents)
end))

task.spawn(function()
    local failures = 0
    local lastStatus = 0
    while alive do
        local ok, problem = pcall(function()
            if pendingAction == "disconnect" then
                pendingAction = nil
                enabled = false
                if connected then post("/pause", {}) end
                connected = false
                ui({status="Disconnected · cache saved",connected=false})
            elseif pendingAction == "connect" then
                pendingAction = nil
                enabled = true
                connected = false
                lastStatus = 0
            end
            if not enabled then return end
            if RunService:IsRunning() then
                if connected and not paused then post("/pause", {}); paused = true end
                ui({status="Paused during Play",connected=false})
                return
            end
            startCollector()
            if not connected or paused then
                ui({status="Indexing metadata…",connected=false,busy=true})
                post("/hello", { placeId = game.PlaceId, jobId = game.JobId, name = game.Name })
                snapshot()
                connected = true
                paused = false
            end
            flush()
            local result = post("/poll", { seq = sequence })
            if result.resync then
                snapshot()
            else
                for _, command in result.commands or {} do answer(command) end
            end
            if pendingAction == "backup" then
                pendingAction = nil
                local saved = post("/ui/backup", {})
                ui({status="Backup saved",connected=true,path=saved.path,
                    detail="Private local backup. Select the path to copy it."})
                lastStatus = os.clock()
            elseif panel.visible() and os.clock() - lastStatus > 5 then
                local state = post("/ui/status", {})
                state.status = "Connected · saved automatically"
                state.connected = true
                ui(state)
                lastStatus = os.clock()
            end
        end)
        if ok then
            failures = 0
        else
            connected = false
            pendingAction = nil
            ui({status="Waiting for Codex / Claude",connected=false,
                detail="Start your AI client or reconnect its roblox_context MCP. Studio may ask for localhost permission."})
            failures = math.min(failures + 1, 5)
        end
        -- Heartbeats carry no source and cause no graph/index rebuilding.
        -- Back off on disconnect; unloading cancels the single worker.
        task.wait(ok and 1 or math.min(2 ^ failures, 30))
    end
end)
