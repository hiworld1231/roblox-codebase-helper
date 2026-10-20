-- Native Studio dock widget. All UI lives outside the game's DataModel.
return function(pluginObject, config, action)
    local ru = config.language == "ru"
    local function t(en, russian) return ru and russian or en end
    local toolbar = pluginObject:CreateToolbar("Codebase Helper")
    local toggle = toolbar:CreateButton("CodebaseHelperPanel", t("Open codebase context", "Открыть контекст проекта"), "", "Codebase")
    toggle.ClickableWhenViewportHidden = true
    local info = DockWidgetPluginGuiInfo.new(Enum.InitialDockState.Right, true, false, 360, 590, 300, 440)
    local widget = pluginObject:CreateDockWidgetPluginGuiAsync("RobloxCodebaseHelper", info)
    widget.Title = "Codebase Helper"
    widget.Name = "RobloxCodebaseHelper"
    widget.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    local isLight = settings().Studio.Theme.Name == "Light"
    local c = isLight and {bg=Color3.fromRGB(245,247,250), surface=Color3.new(1,1,1), text=Color3.fromRGB(22,32,48), muted=Color3.fromRGB(76,90,111), border=Color3.fromRGB(133,147,167), blue=Color3.fromRGB(27,84,208), good=Color3.fromRGB(0,114,78)}
        or {bg=Color3.fromRGB(19,25,35), surface=Color3.fromRGB(28,36,49), text=Color3.fromRGB(238,243,251), muted=Color3.fromRGB(167,182,203), border=Color3.fromRGB(86,105,133), blue=Color3.fromRGB(90,153,255), good=Color3.fromRGB(100,221,174)}
    local function make(className, props, parent)
        local item = Instance.new(className)
        for k,v in props do item[k]=v end
        item.Parent = parent
        return item
    end
    local scroll = make("ScrollingFrame", {Name="Content", Size=UDim2.fromScale(1,1), BackgroundColor3=c.bg, BorderSizePixel=0, ScrollBarThickness=4,
        AutomaticCanvasSize=Enum.AutomaticSize.Y, CanvasSize=UDim2.new(), ScrollingDirection=Enum.ScrollingDirection.Y}, widget)
    make("UIPadding", {PaddingLeft=UDim.new(0,20),PaddingRight=UDim.new(0,20),PaddingTop=UDim.new(0,20),PaddingBottom=UDim.new(0,20)}, scroll)
    make("UIListLayout", {Padding=UDim.new(0,12),SortOrder=Enum.SortOrder.LayoutOrder}, scroll)
    local order = 0
    local function label(parent, name, text, size, bold, color)
        order += 1
        return make("TextLabel", {Name=name,LayoutOrder=order,Size=UDim2.new(1,0,0,0),AutomaticSize=Enum.AutomaticSize.Y,BackgroundTransparency=1,
            Text=text,TextSize=size,Font=bold and Enum.Font.SourceSansSemibold or Enum.Font.SourceSans,TextColor3=color or c.text,
            TextWrapped=true,TextXAlignment=Enum.TextXAlignment.Left,TextYAlignment=Enum.TextYAlignment.Top}, parent)
    end
    label(scroll,"Eyebrow",t("STUDIO / LOCAL CONTEXT", "STUDIO / КОНТЕКСТ ПРОЕКТА"),12,true,c.muted)
    label(scroll,"Heading","Codebase Helper",26,true)
    label(scroll,"Intro",t("Your project, ready for your AI agent.","Проект под рукой у ИИ-агента."),16,false,c.muted)
    local status = label(scroll,"Status",t("Ready to connect", "Готов к подключению"),17,true,c.blue)
    order += 1
    local card = make("Frame",{Name="Project",LayoutOrder=order,Size=UDim2.new(1,0,0,0),AutomaticSize=Enum.AutomaticSize.Y,BackgroundColor3=c.surface,BorderSizePixel=0},scroll)
    make("UICorner",{CornerRadius=UDim.new(0,12)},card)
    make("UIPadding",{PaddingLeft=UDim.new(0,16),PaddingRight=UDim.new(0,16),PaddingTop=UDim.new(0,16),PaddingBottom=UDim.new(0,16)},card)
    make("UIListLayout",{Padding=UDim.new(0,6),SortOrder=Enum.SortOrder.LayoutOrder},card)
    label(card,"ProjectName",game.Name,19,true)
    label(card,"PlaceId","Place ID · "..tostring(game.PlaceId),14,false,c.muted)
    label(card,"ReadOnly",t("Read-only · no game changes", "Только чтение · без изменений игры"),14,true,c.good)
    local count = label(card,"ScriptCount","—",38,true)
    label(card,"CountCaption",t("scripts in the metadata index", "скриптов в индексе метаданных"),15,false,c.muted)
    local cached = label(card,"CachedCount",t("Source is read only when requested.","Код читается только по запросу агента."),15,false,c.muted)
    local primary, disconnect, backup
    local buttons = {}
    local function button(name,text,kind,callback)
        order += 1
        local b = make("TextButton",{Name=name,LayoutOrder=order,Size=UDim2.new(1,0,0,42),Text=text,TextSize=16,Font=Enum.Font.SourceSansSemibold,
            BackgroundColor3=kind=="primary" and c.blue or c.surface,TextColor3=kind=="primary" and (isLight and Color3.new(1,1,1) or Color3.fromRGB(13,26,48)) or c.text,
            BorderSizePixel=0,AutoButtonColor=true,Selectable=true},scroll)
        make("UICorner",{CornerRadius=UDim.new(0,7)},b)
        if kind~="primary" then make("UIStroke",{Color=c.border,Thickness=1,ApplyStrokeMode=Enum.ApplyStrokeMode.Border},b) end
        b.Activated:Connect(function() if b.Active then callback() end end)
        table.insert(buttons,b)
        return b
    end
    primary=button("Connect",t("Connect this project", "Подключить этот проект"),"primary",function() action("connect") end)
    disconnect=button("Disconnect",t("Disconnect", "Отключить"),"secondary",function() action("disconnect") end)
    backup=button("Backup",t("Back up database", "Сохранить копию базы"),"secondary",function() action("backup") end)
    label(scroll,"Autosave",t("The database saves automatically. Backups include metadata, task checkpoints and already cached code.",
        "База сохраняется автоматически. В копию входят индекс, состояние задач и уже прочитанный код."),14,false,c.muted)
    local detail=label(scroll,"Detail",t("Open Codex or Claude, then connect here. Allow localhost access if Studio asks.",
        "Открой Codex или Claude, затем подключись здесь. Если Studio запросит доступ к localhost — разреши его."),15,false,c.muted)
    order += 1
    local location=make("TextBox",{Name="BackupPath",LayoutOrder=order,Size=UDim2.new(1,0,0,60),BackgroundColor3=c.surface,TextColor3=c.text,TextSize=13,
        Font=Enum.Font.Code,TextWrapped=true,TextXAlignment=Enum.TextXAlignment.Left,TextYAlignment=Enum.TextYAlignment.Top,TextEditable=false,
        ClearTextOnFocus=false,MultiLine=true,Text="",Visible=false,BorderSizePixel=0},scroll)
    make("UIPadding",{PaddingLeft=UDim.new(0,8),PaddingRight=UDim.new(0,8),PaddingTop=UDim.new(0,8)},location)
    toggle.Click:Connect(function() widget.Enabled=not widget.Enabled end)
    widget:GetPropertyChangedSignal("Enabled"):Connect(function() toggle:SetActive(widget.Enabled) end)
    toggle:SetActive(widget.Enabled)
    local panel = {}
    function panel.update(data)
        status.Text=data.status or status.Text
        if data.scripts then count.Text=tostring(data.scripts) end
        if data.cachedScripts then cached.Text=t("Code cached on request: ","Код прочитан по запросу: ")..tostring(data.cachedScripts).." / "..tostring(data.scripts) end
        if data.detail then detail.Text=data.detail end
        if data.path then location.Text=data.path;location.Visible=true end
        local ready=data.connected==true
        primary.Text=ready and t("Refresh metadata index", "Обновить индекс метаданных") or t("Connect this project", "Подключить этот проект")
        for _,b in buttons do
            b.Active=not data.busy and (b==primary or ready)
            b.AutoButtonColor=b.Active
            b.TextTransparency=b.Active and 0 or 0.45
        end
    end
    function panel.visible() return widget.Enabled end
    function panel.destroy() widget:Destroy(); toolbar:Destroy() end
    panel.update({connected=false})
    return panel
end
