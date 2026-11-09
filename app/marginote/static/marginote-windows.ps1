# Marginote : envoyer depuis Windows, sans ouvrir l'application.
#
#   Ctrl+Alt+M   envoie le passage que vous venez de copier (Ctrl+C), depuis n'importe quelle application :
#                un lecteur de PDF, un navigateur, Word. Trouvé dans un de vos PDF, il est gardé avec sa page ;
#                sinon, il attend dans « À trier ».
#   Ctrl+Alt+N   le même, avec un commentaire.
#   Clic droit sur un PDF ou une image > Envoyer vers > Marginote.
#
# Lancez ce fichier une fois (Réglages de Marginote dit comment). Il ne demande aucun droit d'administrateur
# et n'installe rien d'autre que : un petit script et votre clé d'envoi dans %LOCALAPPDATA%\Marginote, deux
# raccourcis dans le menu Démarrer et un dans « Envoyer vers ». Pour tout retirer : supprimez ce dossier et
# ces trois raccourcis « Marginote », puis supprimez la clé dans Réglages.

$ErrorActionPreference = 'Stop'
$Server = '__SERVER__'
$Key = '__KEY__'

$SendScript = @'
# Marginote : envoie le passage copié, ou des fichiers (voir l'installateur). Appelé par les raccourcis.
param([string]$Mode = 'passage', [Parameter(ValueFromRemainingArguments = $true)][string[]]$Paths)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Server = (Get-Content -LiteralPath (Join-Path $Here 'server.txt') -Raw).Trim().TrimEnd('/')
$Key = (Get-Content -LiteralPath (Join-Path $Here 'key.txt') -Raw).Trim()
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http

function Show-Note([string]$Title, [string]$Text) {
    try {
        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $null = [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $t = [Security.SecurityElement]::Escape($Title)
        $b = [Security.SecurityElement]::Escape($Text)
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$t</text><text>$b</text></binding></visual></toast>")
        $app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show((New-Object Windows.UI.Notifications.ToastNotification $xml))
    } catch {
        Add-Type -AssemblyName System.Windows.Forms
        $icon = New-Object System.Windows.Forms.NotifyIcon
        $icon.Icon = [System.Drawing.SystemIcons]::Information
        $icon.Visible = $true
        $icon.ShowBalloonTip(6000, $Title, $Text, [System.Windows.Forms.ToolTipIcon]::Info)
        Start-Sleep -Seconds 7
        $icon.Dispose()
    }
}

function New-Client {
    $client = New-Object System.Net.Http.HttpClient
    $client.Timeout = [TimeSpan]::FromMinutes(15)
    $client.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $Key)
    return $client
}

function Read-Answer($response) {
    $body = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
    $text = [Text.Encoding]::UTF8.GetString($body)
    if (-not $response.IsSuccessStatusCode) { throw ('HTTP ' + [int]$response.StatusCode + ' ' + $text) }
    return ($text | ConvertFrom-Json)
}

function Send-Passage($Body) {
    $client = New-Client
    try {
        $json = $Body | ConvertTo-Json -Compress
        $content = New-Object System.Net.Http.StringContent($json, [Text.Encoding]::UTF8, 'application/json')
        return Read-Answer ($client.PostAsync($Server + '/api/send/passage', $content).GetAwaiter().GetResult())
    } finally { $client.Dispose() }
}

function Send-File([string]$File) {
    $ext = [IO.Path]::GetExtension($File).ToLowerInvariant()
    if ($ext -eq '.pdf') { $path = '/api/send/pdf'; $type = 'application/pdf' }
    elseif (@('.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.gif', '.bmp', '.tif', '.tiff') -contains $ext) {
        $path = '/api/send/photo'; $type = 'application/octet-stream'
    }
    else { return ('Ni un PDF ni une image : ' + [IO.Path]::GetFileName($File)) }
    $client = New-Client
    $stream = [IO.File]::OpenRead($File)
    try {
        $form = New-Object System.Net.Http.MultipartFormDataContent
        $part = New-Object System.Net.Http.StreamContent($stream)
        $part.Headers.ContentType = New-Object System.Net.Http.Headers.MediaTypeHeaderValue($type)
        $form.Add($part, 'file', [IO.Path]::GetFileName($File))
        return (Read-Answer ($client.PostAsync($Server + $path, $form).GetAwaiter().GetResult())).say
    } finally { $stream.Dispose(); $client.Dispose() }
}

function Ask-Note {
    Add-Type -AssemblyName System.Windows.Forms
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Marginote'
    $form.Width = 460; $form.Height = 260
    $form.TopMost = $true
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false; $form.MinimizeBox = $false
    $label = New-Object System.Windows.Forms.Label
    $label.Text = 'Votre commentaire sur ce passage :'
    $label.SetBounds(12, 10, 420, 20)
    $box = New-Object System.Windows.Forms.TextBox
    $box.Multiline = $true; $box.ScrollBars = 'Vertical'; $box.AcceptsReturn = $true
    $box.SetBounds(12, 34, 420, 120)
    $ok = New-Object System.Windows.Forms.Button
    $ok.Text = 'Envoyer'; $ok.DialogResult = 'OK'; $ok.SetBounds(256, 168, 85, 30)
    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = 'Annuler'; $cancel.DialogResult = 'Cancel'; $cancel.SetBounds(347, 168, 85, 30)
    $form.Controls.AddRange(@($label, $box, $ok, $cancel))
    $form.AcceptButton = $ok; $form.CancelButton = $cancel
    $form.Add_Shown({ $form.Activate(); $box.Focus() })
    if ($form.ShowDialog() -ne 'OK') { return $null }
    return $box.Text.Trim()
}

try {
    if ($Mode -eq 'file') {
        $lines = @(foreach ($f in $Paths) { Send-File $f })
        Show-Note 'Marginote' ($lines -join "`n")
        exit
    }
    $files = $null
    try { $files = Get-Clipboard -Format FileDropList -ErrorAction SilentlyContinue } catch { $files = $null }
    if ($files) {
        $lines = @(foreach ($f in $files) { Send-File $f.FullName })
        Show-Note 'Marginote' ($lines -join "`n")
        exit
    }
    $text = Get-Clipboard -Raw
    if (-not $text -or -not $text.Trim()) {
        Show-Note 'Marginote' 'Rien à envoyer : sélectionnez un passage, copiez-le (Ctrl+C), puis Ctrl+Alt+M.'
        exit
    }
    $text = $text.Trim()
    # the same passage twice in a row is sent once
    $last = Join-Path $Here 'last.txt'
    $sha = [BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($text)))
    if ((Test-Path -LiteralPath $last) -and ((Get-Content -LiteralPath $last -Raw).Trim() -eq $sha) -and
        ((Get-Item -LiteralPath $last).LastWriteTime -gt (Get-Date).AddMinutes(-10))) {
        Show-Note 'Marginote' 'Déjà envoyé. Copiez le passage suivant (Ctrl+C), puis Ctrl+Alt+M.'
        exit
    }
    $body = @{ text = $text; origin = 'windows' }
    if ($text -match '^https?://\S+$') { $body = @{ url = $text; origin = 'windows' } }
    if ($Mode -eq 'note') {
        $note = Ask-Note
        if ($null -eq $note) { exit }
        if ($note) { $body.note = $note }
    }
    $answer = Send-Passage $body
    Set-Content -LiteralPath $last -Value $sha
    Show-Note 'Marginote' $answer.say
} catch {
    $message = "$($_.Exception.Message)"
    if ($message -match 'HTTP 401') { $message = 'La clé d''envoi ne marche plus : créez-en une dans Marginote > Réglages, puis relancez l''installateur.' }
    elseif ($message -match 'HTTP 413') { $message = 'Fichier trop gros pour Marginote.' }
    elseif ($message -match 'HTTP 415') { $message = 'Ce fichier ne peut pas être lu (PDF abîmé ?).' }
    elseif ($message -match 'HTTP \d+') { $message = 'Marginote a refusé : ' + $message }
    else { $message = 'Marginote est injoignable. Tailscale est-il activé ?' }
    Show-Note 'Marginote : pas envoyé' $message
}
'@

$Dir = Join-Path $env:LOCALAPPDATA 'Marginote'
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
Set-Content -LiteralPath (Join-Path $Dir 'server.txt') -Value $Server -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Dir 'key.txt') -Value $Key -Encoding ASCII
Set-Content -LiteralPath (Join-Path $Dir 'send.ps1') -Value $SendScript -Encoding UTF8

$PowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$Shell = New-Object -ComObject WScript.Shell
function New-Link([string]$Path, [string]$Mode, [string]$Hotkey, [string]$About) {
    $link = $Shell.CreateShortcut($Path)
    $link.TargetPath = $PowerShell
    $link.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + (Join-Path $Dir 'send.ps1') + '" -Mode ' + $Mode
    $link.WorkingDirectory = $Dir
    $link.WindowStyle = 7
    $link.Description = $About
    if ($Hotkey) { $link.Hotkey = $Hotkey }
    $link.Save()
}
$Programs = [Environment]::GetFolderPath('Programs')
New-Link (Join-Path $Programs 'Marginote - envoyer le passage copié.lnk') 'passage' 'CTRL+ALT+M' 'Envoie à Marginote le passage copié'
New-Link (Join-Path $Programs 'Marginote - passage et commentaire.lnk') 'note' 'CTRL+ALT+N' 'Envoie à Marginote le passage copié, avec un commentaire'
New-Link (Join-Path ([Environment]::GetFolderPath('SendTo')) 'Marginote.lnk') 'file' '' 'Envoie à Marginote un PDF ou une image'

# a first call, to check the key and the address
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
try {
    $answer = Invoke-RestMethod -Uri ($Server.TrimEnd('/') + '/api/send/check') -Headers @{ Authorization = 'Bearer ' + $Key } -TimeoutSec 20
    Write-Host ''
    Write-Host '  C''est prêt.' -ForegroundColor Green
    Write-Host '  Copiez un passage (Ctrl+C), puis Ctrl+Alt+M : une notification dit où il est gardé.'
    Write-Host '  Si Ctrl+Alt+M ne fait rien, fermez votre session Windows et rouvrez-la, une fois.'
    Write-Host ''
} catch {
    Write-Host ''
    Write-Host '  Installé, mais Marginote ne répond pas encore.' -ForegroundColor Yellow
    Write-Host '  Vérifiez que Tailscale est activé sur ce PC, puis essayez Ctrl+Alt+M.'
    Write-Host ''
}
# this file holds the key: it is not needed any more (the key is kept in %LOCALAPPDATA%\Marginote)
if ($PSCommandPath) { Remove-Item -LiteralPath $PSCommandPath -ErrorAction SilentlyContinue }
