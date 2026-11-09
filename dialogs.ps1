# MyServer Windows Forms Dialog Helper
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$action = $args[0]

function Show-OneInput {
    param($title, $msg, $lbl, $def)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(430, 210)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $infoLabel = New-Object System.Windows.Forms.Label
    $infoLabel.Location = New-Object System.Drawing.Point(20, 15)
    $infoLabel.Size = New-Object System.Drawing.Size(375, 25)
    $infoLabel.Text = $msg
    $infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $form.Controls.Add($infoLabel)

    $l = New-Object System.Windows.Forms.Label
    $l.Location = New-Object System.Drawing.Point(20, 48)
    $l.Size = New-Object System.Drawing.Size(375, 18)
    $l.Text = $lbl
    $form.Controls.Add($l)

    $t = New-Object System.Windows.Forms.TextBox
    $t.Location = New-Object System.Drawing.Point(20, 68)
    $t.Size = New-Object System.Drawing.Size(375, 25)
    $t.Text = $def
    $form.Controls.Add($t)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(210, 120)
    $btnOk.Size = New-Object System.Drawing.Size(85, 28)
    $btnOk.Text = "OK"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(310, 120)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Cancel"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; val = $t.Text.Trim() }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-TwoInputs {
    param($title, $msg, $lbl1, $def1, $lbl2, $def2, $isPass2=$false)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(430, 250)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $infoLabel = New-Object System.Windows.Forms.Label
    $infoLabel.Location = New-Object System.Drawing.Point(20, 15)
    $infoLabel.Size = New-Object System.Drawing.Size(375, 25)
    $infoLabel.Text = $msg
    $infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $form.Controls.Add($infoLabel)

    $l1 = New-Object System.Windows.Forms.Label
    $l1.Location = New-Object System.Drawing.Point(20, 48)
    $l1.Size = New-Object System.Drawing.Size(375, 18)
    $l1.Text = $lbl1
    $form.Controls.Add($l1)

    $t1 = New-Object System.Windows.Forms.TextBox
    $t1.Location = New-Object System.Drawing.Point(20, 68)
    $t1.Size = New-Object System.Drawing.Size(375, 25)
    $t1.Text = $def1
    $form.Controls.Add($t1)

    $l2 = New-Object System.Windows.Forms.Label
    $l2.Location = New-Object System.Drawing.Point(20, 100)
    $l2.Size = New-Object System.Drawing.Size(375, 18)
    $l2.Text = $lbl2
    $form.Controls.Add($l2)

    $t2 = New-Object System.Windows.Forms.TextBox
    $t2.Location = New-Object System.Drawing.Point(20, 120)
    $t2.Size = New-Object System.Drawing.Size(375, 25)
    $t2.Text = $def2
    if ($isPass2 -eq $true -or $isPass2 -eq "true") {
        $t2.UseSystemPasswordChar = $true
    }
    $form.Controls.Add($t2)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(210, 165)
    $btnOk.Size = New-Object System.Drawing.Size(85, 28)
    $btnOk.Text = "OK"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(310, 165)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Cancel"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; val1 = $t1.Text.Trim(); val2 = $t2.Text.Trim() }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-ThreeInputs {
    param($title, $msg, $lbl1, $def1, $lbl2, $def2, $lbl3, $def3)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(450, 310)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $infoLabel = New-Object System.Windows.Forms.Label
    $infoLabel.Location = New-Object System.Drawing.Point(20, 12)
    $infoLabel.Size = New-Object System.Drawing.Size(395, 30)
    $infoLabel.Text = $msg
    $infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $form.Controls.Add($infoLabel)

    $l1 = New-Object System.Windows.Forms.Label
    $l1.Location = New-Object System.Drawing.Point(20, 48)
    $l1.Size = New-Object System.Drawing.Size(395, 18)
    $l1.Text = $lbl1
    $form.Controls.Add($l1)

    $t1 = New-Object System.Windows.Forms.TextBox
    $t1.Location = New-Object System.Drawing.Point(20, 68)
    $t1.Size = New-Object System.Drawing.Size(395, 25)
    $t1.Text = $def1
    $form.Controls.Add($t1)

    $l2 = New-Object System.Windows.Forms.Label
    $l2.Location = New-Object System.Drawing.Point(20, 98)
    $l2.Size = New-Object System.Drawing.Size(395, 18)
    $l2.Text = $lbl2
    $form.Controls.Add($l2)

    $t2 = New-Object System.Windows.Forms.TextBox
    $t2.Location = New-Object System.Drawing.Point(20, 118)
    $t2.Size = New-Object System.Drawing.Size(395, 25)
    $t2.Text = $def2
    $form.Controls.Add($t2)

    $l3 = New-Object System.Windows.Forms.Label
    $l3.Location = New-Object System.Drawing.Point(20, 148)
    $l3.Size = New-Object System.Drawing.Size(395, 18)
    $l3.Text = $lbl3
    $form.Controls.Add($l3)

    $t3 = New-Object System.Windows.Forms.TextBox
    $t3.Location = New-Object System.Drawing.Point(20, 168)
    $t3.Size = New-Object System.Drawing.Size(395, 25)
    $t3.Text = $def3
    $form.Controls.Add($t3)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(230, 220)
    $btnOk.Size = New-Object System.Drawing.Size(85, 28)
    $btnOk.Text = "OK"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(330, 220)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Cancel"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; val1 = $t1.Text.Trim(); val2 = $t2.Text.Trim(); val3 = $t3.Text.Trim() }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-ChooseZip {
    param($title)
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = $title
    $dlg.Filter = "ZIP Files (*.zip)|*.zip|All files (*.*)|*.*"
    $dlg.CheckFileExists = $true
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; file = $dlg.FileName }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-SaveLog {
    param($title, $defName)
    $dlg = New-Object System.Windows.Forms.SaveFileDialog
    $dlg.Title = $title
    $dlg.Filter = "Text Files (*.txt;*.log)|*.txt;*.log|All Files (*.*)|*.*"
    $dlg.FileName = $defName
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; file = $dlg.FileName }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        Write-Output '{"status":"cancel"}'
    }
}

function Show-SaveZip {
    param($title, $defName)
    $dlg = New-Object System.Windows.Forms.SaveFileDialog
    $dlg.Title = $title
    $dlg.Filter = "ZIP Archive (*.zip)|*.zip"
    $dlg.FileName = $defName
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; file = $dlg.FileName }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-ChooseFolder {
    param($desc)
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = $desc
    $dlg.ShowNewFolderButton = $true
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{ status = "ok"; path = $dlg.SelectedPath }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-CreateTaskDialog {
    param($title, $folderPath, $defLabel, $defServerPath)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(470, 360)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $info = New-Object System.Windows.Forms.Label
    $info.Location = New-Object System.Drawing.Point(20, 12)
    $info.Size = New-Object System.Drawing.Size(415, 30)
    $info.Text = "Folder: " + $folderPath
    $info.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($info)

    $l1 = New-Object System.Windows.Forms.Label
    $l1.Location = New-Object System.Drawing.Point(20, 48)
    $l1.Size = New-Object System.Drawing.Size(415, 18)
    $l1.Text = "Nama / Label Task:"
    $form.Controls.Add($l1)

    $t1 = New-Object System.Windows.Forms.TextBox
    $t1.Location = New-Object System.Drawing.Point(20, 68)
    $t1.Size = New-Object System.Drawing.Size(415, 25)
    $t1.Text = $defLabel
    $form.Controls.Add($t1)

    $l2 = New-Object System.Windows.Forms.Label
    $l2.Location = New-Object System.Drawing.Point(20, 100)
    $l2.Size = New-Object System.Drawing.Size(415, 18)
    $l2.Text = "Target Path di Server (pastikan folder ada):"
    $form.Controls.Add($l2)

    $t2 = New-Object System.Windows.Forms.TextBox
    $t2.Location = New-Object System.Drawing.Point(20, 120)
    $t2.Size = New-Object System.Drawing.Size(415, 25)
    $t2.Text = $defServerPath
    $form.Controls.Add($t2)

    $l3 = New-Object System.Windows.Forms.Label
    $l3.Location = New-Object System.Drawing.Point(20, 155)
    $l3.Size = New-Object System.Drawing.Size(415, 18)
    $l3.Text = "Mode Sinkronisasi / Tipe Cadangan:"
    $form.Controls.Add($l3)

    $r1 = New-Object System.Windows.Forms.RadioButton
    $r1.Location = New-Object System.Drawing.Point(25, 175)
    $r1.Size = New-Object System.Drawing.Size(410, 24)
    $r1.Text = "Backup 1-Arah / Mirroring (Laptop Send-Only -> Server Receive-Only)"
    $r1.Checked = $true
    $form.Controls.Add($r1)

    $r2 = New-Object System.Windows.Forms.RadioButton
    $r2.Location = New-Object System.Drawing.Point(25, 202)
    $r2.Size = New-Object System.Drawing.Size(410, 24)
    $r2.Text = "Sinkronisasi 2-Arah (Send & Receive di kedua perangkat)"
    $form.Controls.Add($r2)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(250, 260)
    $btnOk.Size = New-Object System.Drawing.Size(85, 28)
    $btnOk.Text = "OK"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(350, 260)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Cancel"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $mode = if ($r1.Checked) { "sendonly" } else { "sendreceive" }
        $out = @{ status = "ok"; label = $t1.Text.Trim(); serverPath = $t2.Text.Trim(); mode = $mode }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-ConfigBackupDualDialog {
    param($title, $srvName, $lanMode, $lanIp, $lanPort, $wanUrl, $apiKey, $routeMode="auto")
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(500, 520)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $info = New-Object System.Windows.Forms.Label
    $info.Location = New-Object System.Drawing.Point(20, 10)
    $info.Size = New-Object System.Drawing.Size(445, 30)
    $info.Text = "Konfigurasi Jalur Dinamis Syncthing untuk '$srvName':"
    $info.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($info)

    # 1. Bagian Jalur Lokal (LAN)
    $lblLan = New-Object System.Windows.Forms.Label
    $lblLan.Location = New-Object System.Drawing.Point(20, 44)
    $lblLan.Size = New-Object System.Drawing.Size(445, 18)
    $lblLan.Text = "1. Jalur Lokal / LAN (IP atau Host Syncthing Mandiri):"
    $lblLan.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($lblLan)

    $rLanAuto = New-Object System.Windows.Forms.RadioButton
    $rLanAuto.Location = New-Object System.Drawing.Point(30, 64)
    $rLanAuto.Size = New-Object System.Drawing.Size(435, 20)
    $rLanAuto.Text = "Otomatis / Dinamis (Deteksi IP/Host Server Mandiri)"
    $rLanAuto.Checked = ($lanMode -ne "custom")
    $form.Controls.Add($rLanAuto)

    $rLanCustom = New-Object System.Windows.Forms.RadioButton
    $rLanCustom.Location = New-Object System.Drawing.Point(30, 84)
    $rLanCustom.Size = New-Object System.Drawing.Size(435, 20)
    $rLanCustom.Text = "Manual / IP LAN atau Host Kustom (Mandiri)"
    $rLanCustom.Checked = ($lanMode -eq "custom")
    $form.Controls.Add($rLanCustom)

    $tLanIp = New-Object System.Windows.Forms.TextBox
    $tLanIp.Location = New-Object System.Drawing.Point(50, 108)
    $tLanIp.Size = New-Object System.Drawing.Size(270, 24)
    $tLanIp.Text = $lanIp
    $tLanIp.Enabled = $rLanCustom.Checked
    $form.Controls.Add($tLanIp)

    $lblLanPort = New-Object System.Windows.Forms.Label
    $lblLanPort.Location = New-Object System.Drawing.Point(330, 111)
    $lblLanPort.Size = New-Object System.Drawing.Size(35, 18)
    $lblLanPort.Text = "Port:"
    $form.Controls.Add($lblLanPort)

    $tLanPort = New-Object System.Windows.Forms.TextBox
    $tLanPort.Location = New-Object System.Drawing.Point(370, 108)
    $tLanPort.Size = New-Object System.Drawing.Size(95, 24)
    $tLanPort.Text = if ($lanPort) { $lanPort } else { "8384" }
    $form.Controls.Add($tLanPort)

    $rLanAuto.Add_CheckedChanged({
        $tLanIp.Enabled = $rLanCustom.Checked
        if ($rLanAuto.Checked) { $tLanIp.Text = "" }
    })
    $rLanCustom.Add_CheckedChanged({
        $tLanIp.Enabled = $rLanCustom.Checked
    })

    # 2. Bagian Jalur Publik (WAN)
    $lblWan = New-Object System.Windows.Forms.Label
    $lblWan.Location = New-Object System.Drawing.Point(20, 144)
    $lblWan.Size = New-Object System.Drawing.Size(445, 18)
    $lblWan.Text = "2. Jalur Publik / WAN (Domain Syncthing Mandiri):"
    $lblWan.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($lblWan)

    $lblWanDesc = New-Object System.Windows.Forms.Label
    $lblWanDesc.Location = New-Object System.Drawing.Point(30, 164)
    $lblWanDesc.Size = New-Object System.Drawing.Size(435, 18)
    $lblWanDesc.Text = "Subdomain / URL Syncthing Publik (contoh: https://sync.domain.com):"
    $form.Controls.Add($lblWanDesc)

    $tWanUrl = New-Object System.Windows.Forms.TextBox
    $tWanUrl.Location = New-Object System.Drawing.Point(30, 184)
    $tWanUrl.Size = New-Object System.Drawing.Size(435, 24)
    $tWanUrl.Text = $wanUrl
    $form.Controls.Add($tWanUrl)

    # 3. Bagian Mode Pemilihan Rute
    $lblRoute = New-Object System.Windows.Forms.Label
    $lblRoute.Location = New-Object System.Drawing.Point(20, 220)
    $lblRoute.Size = New-Object System.Drawing.Size(445, 18)
    $lblRoute.Text = "3. Mode Pemilihan Rute (Tanpa Terikat IP ZimaOS):"
    $lblRoute.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($lblRoute)

    $rRouteAuto = New-Object System.Windows.Forms.RadioButton
    $rRouteAuto.Location = New-Object System.Drawing.Point(30, 240)
    $rRouteAuto.Size = New-Object System.Drawing.Size(435, 20)
    $rRouteAuto.Text = "Otomatis / Dinamis (Uji & pilih jalur aktif mandiri)"
    $rRouteAuto.Checked = ($routeMode -ne "lan" -and $routeMode -ne "wan")
    $form.Controls.Add($rRouteAuto)

    $rRouteLan = New-Object System.Windows.Forms.RadioButton
    $rRouteLan.Location = New-Object System.Drawing.Point(30, 260)
    $rRouteLan.Size = New-Object System.Drawing.Size(435, 20)
    $rRouteLan.Text = "Selalu Gunakan Jalur Lokal (LAN)"
    $rRouteLan.Checked = ($routeMode -eq "lan")
    $form.Controls.Add($rRouteLan)

    $rRouteWan = New-Object System.Windows.Forms.RadioButton
    $rRouteWan.Location = New-Object System.Drawing.Point(30, 280)
    $rRouteWan.Size = New-Object System.Drawing.Size(435, 20)
    $rRouteWan.Text = "Selalu Gunakan Jalur Domain / WAN"
    $rRouteWan.Checked = ($routeMode -eq "wan")
    $form.Controls.Add($rRouteWan)

    # 4. Bagian REST API Key
    $lblKey = New-Object System.Windows.Forms.Label
    $lblKey.Location = New-Object System.Drawing.Point(20, 312)
    $lblKey.Size = New-Object System.Drawing.Size(445, 18)
    $lblKey.Text = "4. REST API Key Syncthing Server (Wajib untuk kontrol & task):"
    $lblKey.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($lblKey)

    $tKey = New-Object System.Windows.Forms.TextBox
    $tKey.Location = New-Object System.Drawing.Point(30, 332)
    $tKey.Size = New-Object System.Drawing.Size(435, 24)
    $tKey.Text = $apiKey
    $form.Controls.Add($tKey)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(280, 420)
    $btnOk.Size = New-Object System.Drawing.Size(85, 28)
    $btnOk.Text = "OK"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(380, 420)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Cancel"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $finalLanMode = if ($rLanCustom.Checked) { "custom" } else { "inherit" }
        $finalRouteMode = if ($rRouteLan.Checked) { "lan" } elseif ($rRouteWan.Checked) { "wan" } else { "auto" }
        $out = @{
            status = "ok"
            routeMode = $finalRouteMode
            lanMode = $finalLanMode
            lanIp = $tLanIp.Text.Trim()
            lanPort = $tLanPort.Text.Trim()
            wanUrl = $tWanUrl.Text.Trim()
            apiKey = $tKey.Text.Trim()
        }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-AccountSetup {
    param($title, $msg, $lbl1, $def1, $lbl2, $def2, $lbl3, $def3)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(450, 320)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $infoLabel = New-Object System.Windows.Forms.Label
    $infoLabel.Location = New-Object System.Drawing.Point(20, 12)
    $infoLabel.Size = New-Object System.Drawing.Size(395, 30)
    $infoLabel.Text = $msg
    $infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $form.Controls.Add($infoLabel)

    # 1. Profile Name
    $l1 = New-Object System.Windows.Forms.Label
    $l1.Location = New-Object System.Drawing.Point(20, 48)
    $l1.Size = New-Object System.Drawing.Size(395, 18)
    $l1.Text = $lbl1
    $form.Controls.Add($l1)

    $t1 = New-Object System.Windows.Forms.TextBox
    $t1.Location = New-Object System.Drawing.Point(20, 68)
    $t1.Size = New-Object System.Drawing.Size(395, 25)
    $t1.Text = $def1
    $form.Controls.Add($t1)

    # 2. Username
    $l2 = New-Object System.Windows.Forms.Label
    $l2.Location = New-Object System.Drawing.Point(20, 98)
    $l2.Size = New-Object System.Drawing.Size(395, 18)
    $l2.Text = $lbl2
    $form.Controls.Add($l2)

    $t2 = New-Object System.Windows.Forms.TextBox
    $t2.Location = New-Object System.Drawing.Point(20, 118)
    $t2.Size = New-Object System.Drawing.Size(395, 25)
    $t2.Text = $def2
    $form.Controls.Add($t2)

    # 3. Password (masked)
    $l3 = New-Object System.Windows.Forms.Label
    $l3.Location = New-Object System.Drawing.Point(20, 148)
    $l3.Size = New-Object System.Drawing.Size(395, 18)
    $l3.Text = $lbl3
    $form.Controls.Add($l3)

    $t3 = New-Object System.Windows.Forms.TextBox
    $t3.Location = New-Object System.Drawing.Point(20, 168)
    $t3.Size = New-Object System.Drawing.Size(395, 25)
    $t3.Text = $def3
    $t3.UseSystemPasswordChar = $true
    $form.Controls.Add($t3)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(230, 225)
    $btnOk.Size = New-Object System.Drawing.Size(85, 28)
    $btnOk.Text = "OK"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(330, 225)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Cancel"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{
            status = "ok"
            val1 = $t1.Text.Trim()
            val2 = $t2.Text.Trim()
            val3 = $t3.Text.Trim()
            username = $t2.Text.Trim()
            password = $t3.Text.Trim()
        }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-SetupWizard {
    param($title, $msg, $lbl1, $def1, $lbl2, $def2, $lbl3, $def3, $lbl4, $def4, $def5="", $def6="")
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(480, 520)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $infoLabel = New-Object System.Windows.Forms.Label
    $infoLabel.Location = New-Object System.Drawing.Point(20, 10)
    $infoLabel.Size = New-Object System.Drawing.Size(425, 30)
    $infoLabel.Text = $msg
    $infoLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $form.Controls.Add($infoLabel)

    # 1. Server Name
    $l1 = New-Object System.Windows.Forms.Label
    $l1.Location = New-Object System.Drawing.Point(20, 45)
    $l1.Size = New-Object System.Drawing.Size(425, 18)
    $l1.Text = $lbl1
    $form.Controls.Add($l1)

    $t1 = New-Object System.Windows.Forms.TextBox
    $t1.Location = New-Object System.Drawing.Point(20, 65)
    $t1.Size = New-Object System.Drawing.Size(425, 23)
    $t1.Text = $def1
    $form.Controls.Add($t1)

    # 2. Server URL
    $l2 = New-Object System.Windows.Forms.Label
    $l2.Location = New-Object System.Drawing.Point(20, 93)
    $l2.Size = New-Object System.Drawing.Size(425, 18)
    $l2.Text = $lbl2
    $form.Controls.Add($l2)

    $t2 = New-Object System.Windows.Forms.TextBox
    $t2.Location = New-Object System.Drawing.Point(20, 113)
    $t2.Size = New-Object System.Drawing.Size(425, 23)
    $t2.Text = $def2
    $form.Controls.Add($t2)

    # 3. Username & Password in row
    $l3 = New-Object System.Windows.Forms.Label
    $l3.Location = New-Object System.Drawing.Point(20, 141)
    $l3.Size = New-Object System.Drawing.Size(205, 18)
    $l3.Text = $lbl3
    $form.Controls.Add($l3)

    $t3 = New-Object System.Windows.Forms.TextBox
    $t3.Location = New-Object System.Drawing.Point(20, 161)
    $t3.Size = New-Object System.Drawing.Size(205, 23)
    $t3.Text = $def3
    $form.Controls.Add($t3)

    $l4 = New-Object System.Windows.Forms.Label
    $l4.Location = New-Object System.Drawing.Point(240, 141)
    $l4.Size = New-Object System.Drawing.Size(205, 18)
    $l4.Text = $lbl4
    $form.Controls.Add($l4)

    $t4 = New-Object System.Windows.Forms.TextBox
    $t4.Location = New-Object System.Drawing.Point(240, 161)
    $t4.Size = New-Object System.Drawing.Size(205, 23)
    $t4.Text = $def4
    $t4.UseSystemPasswordChar = $true
    $form.Controls.Add($t4)

    # Auto-Detect Button
    $btnAutoDetect = New-Object System.Windows.Forms.Button
    $btnAutoDetect.Location = New-Object System.Drawing.Point(20, 195)
    $btnAutoDetect.Size = New-Object System.Drawing.Size(425, 28)
    $btnAutoDetect.Text = "⚡ Deteksi Otomatis Remote ID dari Server"
    $btnAutoDetect.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($btnAutoDetect)

    $statusDetect = New-Object System.Windows.Forms.Label
    $statusDetect.Location = New-Object System.Drawing.Point(20, 226)
    $statusDetect.Size = New-Object System.Drawing.Size(425, 18)
    $statusDetect.Text = "Klik tombol di atas untuk mendeteksi Remote ID & Virtual IP otomatis."
    $statusDetect.ForeColor = [System.Drawing.Color]::Gray
    $form.Controls.Add($statusDetect)

    # 5. Remote ID (ZeroTier Network ID 16-hex)
    $l5 = New-Object System.Windows.Forms.Label
    $l5.Location = New-Object System.Drawing.Point(20, 248)
    $l5.Size = New-Object System.Drawing.Size(425, 18)
    $l5.Text = "Remote ID ZimaOS (ZeroTier Network ID 16 Digit Hex):"
    $form.Controls.Add($l5)

    $t5 = New-Object System.Windows.Forms.TextBox
    $t5.Location = New-Object System.Drawing.Point(20, 268)
    $t5.Size = New-Object System.Drawing.Size(425, 23)
    $t5.Text = $def5
    $form.Controls.Add($t5)

    # 6. Virtual Network IP (ZeroTier IP ZimaOS)
    $l6 = New-Object System.Windows.Forms.Label
    $l6.Location = New-Object System.Drawing.Point(20, 298)
    $l6.Size = New-Object System.Drawing.Size(425, 18)
    $l6.Text = "IP Virtual Network ZimaOS (ZeroTier IP Server, misal: 10.x.x.x):"
    $form.Controls.Add($l6)

    $t6 = New-Object System.Windows.Forms.TextBox
    $t6.Location = New-Object System.Drawing.Point(20, 318)
    $t6.Size = New-Object System.Drawing.Size(425, 23)
    $t6.Text = $def6
    $form.Controls.Add($t6)

    # Click Event
    $btnAutoDetect.Add_Click({
        $u = $t2.Text.Trim().TrimEnd('/')
        $usr = $t3.Text.Trim()
        $pwd = $t4.Text
        if (-not $u -or -not $usr) {
            $statusDetect.Text = "Isi URL Server dan Username terlebih dahulu!"
            $statusDetect.ForeColor = [System.Drawing.Color]::Red
            return
        }

        if ($u -notmatch '^https?://') {
            $u = "http://$u"
        }

        $statusDetect.Text = "Menghubungi server..."
        $statusDetect.ForeColor = [System.Drawing.Color]::Blue
        $form.Refresh()

        $detectedNetworkId = ""
        $detectedVirtualIp = ""
        $detectedMethod = ""
        $loginFailed = $false

        try {
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12 -bor [System.Net.SecurityProtocolType]::Tls11 -bor [System.Net.SecurityProtocolType]::Tls
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
            
            $body = @{ username = $usr; name = $usr; password = $pwd } | ConvertTo-Json
            $loginRes = Invoke-RestMethod -Uri "$u/v1/users/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 6
            
            $tok = $null
            if ($loginRes.data) {
                if ($loginRes.data.token) { $tok = $loginRes.data.token }
                elseif ($loginRes.data.access_token) { $tok = $loginRes.data.access_token }
                elseif ($loginRes.data.token_pair -and $loginRes.data.token_pair.access_token) { $tok = $loginRes.data.token_pair.access_token }
                elseif ($loginRes.data -is [string]) { $tok = $loginRes.data }
            }
            if (-not $tok -and $loginRes.token) { $tok = $loginRes.token }
            if (-not $tok -and $loginRes.access_token) { $tok = $loginRes.access_token }

            if ($tok) {
                $ztRes = $null
                try {
                    $headers = @{ "Authorization" = "Bearer $tok"; "token" = "$tok" }
                    $ztRes = Invoke-RestMethod -Uri "$u/v2/zimaos/zt/info" -Method Get -Headers $headers -TimeoutSec 5
                } catch {
                    try {
                        $headers2 = @{ "Authorization" = "$tok"; "token" = "$tok" }
                        $ztRes = Invoke-RestMethod -Uri "$u/v2/zimaos/zt/info" -Method Get -Headers $headers2 -TimeoutSec 5
                    } catch {
                        try {
                            $ztRes = Invoke-RestMethod -Uri "$u/zt/info" -Method Get -Headers $headers -TimeoutSec 5
                        } catch {}
                    }
                }

                if ($ztRes) {
                    $ztData = if ($ztRes.data) { $ztRes.data } else { $ztRes }
                    $detectedNetworkId = if ($ztData.network_id) { $ztData.network_id } elseif ($ztData.networkId) { $ztData.networkId } elseif ($ztData.id) { $ztData.id } else { "" }
                    $detectedVirtualIp = if ($ztData.remote_ipv4) { $ztData.remote_ipv4 } elseif ($ztData.remoteIpv4) { $ztData.remoteIpv4 } elseif ($ztData.ip) { $ztData.ip } else { "" }
                    if ($detectedNetworkId) { $detectedMethod = "REST API Server" }
                }
            } else {
                $loginFailed = $true
                $statusDetect.Text = "Autentikasi gagal. Periksa username dan password."
                $statusDetect.ForeColor = [System.Drawing.Color]::Red
            }
        } catch {
            $errMsg = $_.Exception.Message
            if ($_.Exception.Response) {
                try {
                    $stream = $_.Exception.Response.GetResponseStream()
                    $reader = New-Object System.IO.StreamReader($stream)
                    $errJson = $reader.ReadToEnd() | ConvertFrom-Json
                    if ($errJson.message) { $errMsg = $errJson.message }
                } catch {}
            }
            if ($errMsg -match "password" -or $errMsg -match "credential" -or $errMsg -match "Unauthorized" -or $errMsg -match "does not exist") {
                $loginFailed = $true
                $statusDetect.Text = "Gagal login: Username atau Password salah."
                $statusDetect.ForeColor = [System.Drawing.Color]::Red
            }
        }

        # Fallback 1: Cek konfigurasi Zima Client lokal jika belum terdeteksi dan bukan salah password
        if (-not $detectedNetworkId -and -not $loginFailed) {
            $zimaCfg = "$env:APPDATA\Zima\config.json"
            if (Test-Path $zimaCfg) {
                try {
                    $zc = Get-Content $zimaCfg -Raw | ConvertFrom-Json
                    if ($zc.connection.ztNetwork.networkId) {
                        $detectedNetworkId = $zc.connection.ztNetwork.networkId
                        $detectedVirtualIp = $zc.connection.ztNetwork.remote_ipv4
                        $detectedMethod = "Konfigurasi Zima Client Lokal"
                    }
                } catch {}
            }
        }

        # Fallback 2: Cek daemon ZeroTier lokal (port 9993)
        if (-not $detectedNetworkId -and -not $loginFailed) {
            $ztTokenFile = "$env:ProgramData\ZeroTier\One\authtoken.secret"
            if (Test-Path $ztTokenFile) {
                try {
                    $ztSecret = (Get-Content $ztTokenFile -Raw).Trim()
                    $ztHeaders = @{ "X-ZT1-Auth" = $ztSecret }
                    $ztLocalNetworks = Invoke-RestMethod -Uri "http://127.0.0.1:9993/network" -Headers $ztHeaders -TimeoutSec 3
                    if ($ztLocalNetworks -and $ztLocalNetworks.Count -gt 0) {
                        $netObj = $ztLocalNetworks[0]
                        $detectedNetworkId = $netObj.id
                        if ($netObj.assignedAddresses -and $netObj.assignedAddresses.Count -gt 0) {
                            $detectedVirtualIp = ($netObj.assignedAddresses[0] -split '/')[0]
                        }
                        $detectedMethod = "ZeroTier Service Lokal"
                    }
                } catch {}
            }
        }

        # Evaluasi hasil akhir
        if ($detectedNetworkId) {
            $t5.Text = $detectedNetworkId
            if ($detectedVirtualIp) { $t6.Text = $detectedVirtualIp }
            $statusDetect.Text = "Berhasil dideteksi via $detectedMethod!"
            $statusDetect.ForeColor = [System.Drawing.Color]::DarkGreen
        } elseif (-not $loginFailed) {
            $statusDetect.Text = "Gagal deteksi otomatis. Anda dapat memasukkan ID secara manual."
            $statusDetect.ForeColor = [System.Drawing.Color]::DarkOrange
        }
    })

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(260, 440)
    $btnOk.Size = New-Object System.Drawing.Size(90, 28)
    $btnOk.Text = "Simpan"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(360, 440)
    $btnCancel.Size = New-Object System.Drawing.Size(85, 28)
    $btnCancel.Text = "Batal"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $out = @{
            status = "ok"
            val1 = $t1.Text.Trim()
            val2 = $t2.Text.Trim()
            val3 = $t3.Text.Trim()
            val4 = $t4.Text.Trim()
            val5 = $t5.Text.Trim()
            val6 = $t6.Text.Trim()
            server_name = $t1.Text.Trim()
            server_url = $t2.Text.Trim()
            username = $t3.Text.Trim()
            password = $t4.Text.Trim()
            zerotier_network_id = $t5.Text.Trim()
            zerotier_virtual_ip = $t6.Text.Trim()
        }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-AddDeviceDialog {
    param($title, $serverName, $defDeviceId="", $defDeviceName="", $defAddress="dynamic", $defAutoAccept=$true)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(480, 480)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $info = New-Object System.Windows.Forms.Label
    $info.Location = New-Object System.Drawing.Point(20, 12)
    $info.Size = New-Object System.Drawing.Size(425, 28)
    $info.Text = "Hubungkan perangkat baru untuk sinkronisasi berkas Syncthing:"
    $info.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($info)

    # 1. Target Syncthing
    $lblTarget = New-Object System.Windows.Forms.Label
    $lblTarget.Location = New-Object System.Drawing.Point(20, 44)
    $lblTarget.Size = New-Object System.Drawing.Size(425, 18)
    $lblTarget.Text = "Target Syncthing:"
    $form.Controls.Add($lblTarget)

    $rLocal = New-Object System.Windows.Forms.RadioButton
    $rLocal.Location = New-Object System.Drawing.Point(30, 64)
    $rLocal.Size = New-Object System.Drawing.Size(415, 20)
    $rLocal.Text = "Laptop Saya (Syncthing Lokal)"
    $rLocal.Checked = $true
    $form.Controls.Add($rLocal)

    $rServer = New-Object System.Windows.Forms.RadioButton
    $rServer.Location = New-Object System.Drawing.Point(30, 86)
    $rServer.Size = New-Object System.Drawing.Size(415, 20)
    $srvLabel = if ($serverName) { "Server ($serverName)" } else { "Server Remote" }
    $rServer.Text = $srvLabel
    $form.Controls.Add($rServer)

    $rBoth = New-Object System.Windows.Forms.RadioButton
    $rBoth.Location = New-Object System.Drawing.Point(30, 108)
    $rBoth.Size = New-Object System.Drawing.Size(415, 20)
    $rBoth.Text = "Hubungkan Keduanya (Laptop & Server Saling Terhubung)"
    $form.Controls.Add($rBoth)

    # 2. Device ID
    $lblDevId = New-Object System.Windows.Forms.Label
    $lblDevId.Location = New-Object System.Drawing.Point(20, 138)
    $lblDevId.Size = New-Object System.Drawing.Size(425, 18)
    $lblDevId.Text = "Device ID (ID Perangkat Syncthing):"
    $form.Controls.Add($lblDevId)

    $tDevId = New-Object System.Windows.Forms.TextBox
    $tDevId.Location = New-Object System.Drawing.Point(20, 158)
    $tDevId.Size = New-Object System.Drawing.Size(425, 24)
    $tDevId.Font = New-Object System.Drawing.Font("Consolas", 8.5)
    $tDevId.Text = $defDeviceId
    $form.Controls.Add($tDevId)

    # 3. Device Name / Label
    $lblDevName = New-Object System.Windows.Forms.Label
    $lblDevName.Location = New-Object System.Drawing.Point(20, 192)
    $lblDevName.Size = New-Object System.Drawing.Size(425, 18)
    $lblDevName.Text = "Nama / Label Perangkat (contoh: Laptop Kantor):"
    $form.Controls.Add($lblDevName)

    $tDevName = New-Object System.Windows.Forms.TextBox
    $tDevName.Location = New-Object System.Drawing.Point(20, 212)
    $tDevName.Size = New-Object System.Drawing.Size(425, 24)
    $tDevName.Text = $defDeviceName
    $form.Controls.Add($tDevName)

    # 4. Addresses
    $lblAddr = New-Object System.Windows.Forms.Label
    $lblAddr.Location = New-Object System.Drawing.Point(20, 246)
    $lblAddr.Size = New-Object System.Drawing.Size(425, 18)
    $lblAddr.Text = "Alamat / Addresses (default: dynamic):"
    $form.Controls.Add($lblAddr)

    $tAddr = New-Object System.Windows.Forms.TextBox
    $tAddr.Location = New-Object System.Drawing.Point(20, 266)
    $tAddr.Size = New-Object System.Drawing.Size(425, 24)
    $tAddr.Text = if ($defAddress) { $defAddress } else { "dynamic" }
    $form.Controls.Add($tAddr)

    # 5. Checkboxes
    $chkAutoAccept = New-Object System.Windows.Forms.CheckBox
    $chkAutoAccept.Location = New-Object System.Drawing.Point(25, 304)
    $chkAutoAccept.Size = New-Object System.Drawing.Size(420, 22)
    $chkAutoAccept.Text = "Otomatis terima folder yang dibagikan dari perangkat ini"
    $chkAutoAccept.Checked = ($defAutoAccept -ne $false -and $defAutoAccept -ne "false")
    $form.Controls.Add($chkAutoAccept)

    $chkIntroducer = New-Object System.Windows.Forms.CheckBox
    $chkIntroducer.Location = New-Object System.Drawing.Point(25, 328)
    $chkIntroducer.Size = New-Object System.Drawing.Size(420, 22)
    $chkIntroducer.Text = "Jadikan Introducer (bagikan daftar perangkat lain)"
    $chkIntroducer.Checked = $false
    $form.Controls.Add($chkIntroducer)

    $btnOk = New-Object System.Windows.Forms.Button
    $btnOk.Location = New-Object System.Drawing.Point(235, 385)
    $btnOk.Size = New-Object System.Drawing.Size(105, 30)
    $btnOk.Text = "Hubungkan"
    $btnOk.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnOk
    $form.Controls.Add($btnOk)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(350, 385)
    $btnCancel.Size = New-Object System.Drawing.Size(95, 30)
    $btnCancel.Text = "Batal"
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $target = if ($rBoth.Checked) { "both" } elseif ($rServer.Checked) { "server" } else { "local" }
        $out = @{
            status = "ok"
            target = $target
            device_id = $tDevId.Text.Trim()
            device_name = $tDevName.Text.Trim()
            address = $tAddr.Text.Trim()
            auto_accept = $chkAutoAccept.Checked
            introducer = $chkIntroducer.Checked
        }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

function Show-PendingDeviceDialog {
    param($title, $targetDaemon, $devId, $devName, $devAddress, $devTime)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(500, 440)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $headerPanel = New-Object System.Windows.Forms.Panel
    $headerPanel.Location = New-Object System.Drawing.Point(0, 0)
    $headerPanel.Size = New-Object System.Drawing.Size(500, 55)
    $headerPanel.BackColor = [System.Drawing.Color]::FromArgb(240, 248, 255)
    $form.Controls.Add($headerPanel)

    $headerIcon = New-Object System.Windows.Forms.Label
    $headerIcon.Location = New-Object System.Drawing.Point(15, 12)
    $headerIcon.Size = New-Object System.Drawing.Size(35, 30)
    $headerIcon.Text = "🔔"
    $headerIcon.Font = New-Object System.Drawing.Font("Segoe UI", 16)
    $headerPanel.Controls.Add($headerIcon)

    $headerTitle = New-Object System.Windows.Forms.Label
    $headerTitle.Location = New-Object System.Drawing.Point(55, 10)
    $headerTitle.Size = New-Object System.Drawing.Size(425, 20)
    $headerTitle.Text = "Permintaan Koneksi Perangkat Masuk"
    $headerTitle.Font = New-Object System.Drawing.Font("Segoe UI", 10.5, [System.Drawing.FontStyle]::Bold)
    $headerPanel.Controls.Add($headerTitle)

    $headerSubtitle = New-Object System.Windows.Forms.Label
    $headerSubtitle.Location = New-Object System.Drawing.Point(55, 30)
    $headerSubtitle.Size = New-Object System.Drawing.Size(425, 18)
    $headerSubtitle.Text = "Perangkat lain ingin terhubung ke Syncthing ($targetDaemon)"
    $headerSubtitle.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
    $headerSubtitle.ForeColor = [System.Drawing.Color]::FromArgb(80, 80, 80)
    $headerPanel.Controls.Add($headerSubtitle)

    # Info Details Box
    $infoBox = New-Object System.Windows.Forms.GroupBox
    $infoBox.Location = New-Object System.Drawing.Point(20, 65)
    $infoBox.Size = New-Object System.Drawing.Size(445, 160)
    $infoBox.Text = " Detail Perangkat Pemohon "
    $infoBox.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
    $form.Controls.Add($infoBox)

    $lblDName = New-Object System.Windows.Forms.Label
    $lblDName.Location = New-Object System.Drawing.Point(15, 22)
    $lblDName.Size = New-Object System.Drawing.Size(415, 18)
    $dispName = if ($devName) { $devName } else { "Tidak Diketahui" }
    $lblDName.Text = "Nama Perangkat:  $dispName"
    $lblDName.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $infoBox.Controls.Add($lblDName)

    $lblDId = New-Object System.Windows.Forms.Label
    $lblDId.Location = New-Object System.Drawing.Point(15, 45)
    $lblDId.Size = New-Object System.Drawing.Size(415, 16)
    $lblDId.Text = "Device ID:"
    $infoBox.Controls.Add($lblDId)

    $tDId = New-Object System.Windows.Forms.TextBox
    $tDId.Location = New-Object System.Drawing.Point(15, 63)
    $tDId.Size = New-Object System.Drawing.Size(415, 22)
    $tDId.Text = $devId
    $tDId.ReadOnly = $true
    $tDId.Font = New-Object System.Drawing.Font("Consolas", 8)
    $infoBox.Controls.Add($tDId)

    $lblDAddr = New-Object System.Windows.Forms.Label
    $lblDAddr.Location = New-Object System.Drawing.Point(15, 95)
    $lblDAddr.Size = New-Object System.Drawing.Size(415, 18)
    $dispAddr = if ($devAddress) { $devAddress } else { "Otomatis (Dynamic)" }
    $lblDAddr.Text = "Alamat IP / Host:  $dispAddr"
    $infoBox.Controls.Add($lblDAddr)

    $lblDTime = New-Object System.Windows.Forms.Label
    $lblDTime.Location = New-Object System.Drawing.Point(15, 118)
    $lblDTime.Size = New-Object System.Drawing.Size(415, 18)
    $dispTime = if ($devTime) { $devTime } else { "Baru saja" }
    $lblDTime.Text = "Waktu Permintaan: $dispTime"
    $infoBox.Controls.Add($lblDTime)

    # Name customizer
    $lblCustom = New-Object System.Windows.Forms.Label
    $lblCustom.Location = New-Object System.Drawing.Point(20, 235)
    $lblCustom.Size = New-Object System.Drawing.Size(445, 18)
    $lblCustom.Text = "Simpan sebagai Nama Perangkat:"
    $form.Controls.Add($lblCustom)

    $tCustomName = New-Object System.Windows.Forms.TextBox
    $tCustomName.Location = New-Object System.Drawing.Point(20, 255)
    $tCustomName.Size = New-Object System.Drawing.Size(445, 24)
    $tCustomName.Text = if ($devName) { $devName } else { "Perangkat-Baru" }
    $form.Controls.Add($tCustomName)

    $chkAuto = New-Object System.Windows.Forms.CheckBox
    $chkAuto.Location = New-Object System.Drawing.Point(25, 288)
    $chkAuto.Size = New-Object System.Drawing.Size(440, 22)
    $chkAuto.Text = "Otomatis terima folder yang dibagikan dari perangkat ini"
    $chkAuto.Checked = $true
    $form.Controls.Add($chkAuto)

    # 3 Buttons: Accept, Reject, Later
    $btnAccept = New-Object System.Windows.Forms.Button
    $btnAccept.Location = New-Object System.Drawing.Point(20, 335)
    $btnAccept.Size = New-Object System.Drawing.Size(155, 34)
    $btnAccept.Text = "✔ Izinkan & Hubungkan"
    $btnAccept.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($btnAccept)

    $btnReject = New-Object System.Windows.Forms.Button
    $btnReject.Location = New-Object System.Drawing.Point(185, 335)
    $btnReject.Size = New-Object System.Drawing.Size(140, 34)
    $btnReject.Text = "✖ Tolak Permintaan"
    $form.Controls.Add($btnReject)

    $btnLater = New-Object System.Windows.Forms.Button
    $btnLater.Location = New-Object System.Drawing.Point(335, 335)
    $btnLater.Size = New-Object System.Drawing.Size(130, 34)
    $btnLater.Text = "Tunda / Nanti"
    $form.Controls.Add($btnLater)

    $script:chosenStatus = "ignore"

    $btnAccept.Add_Click({
        $script:chosenStatus = "accept"
        $form.Close()
    })
    $btnReject.Add_Click({
        $script:chosenStatus = "reject"
        $form.Close()
    })
    $btnLater.Add_Click({
        $script:chosenStatus = "ignore"
        $form.Close()
    })

    $form.ShowDialog() | Out-Null
    $out = @{
        status = $script:chosenStatus
        device_id = $devId
        device_name = $tCustomName.Text.Trim()
        auto_accept = $chkAuto.Checked
    }
    Write-Output ($out | ConvertTo-Json -Compress)
}

function Show-MyDeviceIdDialog {
    param($title, $laptopId, $serverId, $serverName)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = $title
    $form.Size = New-Object System.Drawing.Size(520, 300)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    $info = New-Object System.Windows.Forms.Label
    $info.Location = New-Object System.Drawing.Point(20, 12)
    $info.Size = New-Object System.Drawing.Size(465, 32)
    $info.Text = "Salin Device ID ini ke perangkat lain untuk menghubungkan Syncthing:"
    $info.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($info)

    # 1. Laptop ID
    $lblLap = New-Object System.Windows.Forms.Label
    $lblLap.Location = New-Object System.Drawing.Point(20, 48)
    $lblLap.Size = New-Object System.Drawing.Size(465, 18)
    $lblLap.Text = "Device ID Laptop Saya (Lokal):"
    $form.Controls.Add($lblLap)

    $tLap = New-Object System.Windows.Forms.TextBox
    $tLap.Location = New-Object System.Drawing.Point(20, 68)
    $tLap.Size = New-Object System.Drawing.Size(355, 24)
    $tLap.Text = $laptopId
    $tLap.ReadOnly = $true
    $tLap.Font = New-Object System.Drawing.Font("Consolas", 8)
    $form.Controls.Add($tLap)

    $btnCopyLap = New-Object System.Windows.Forms.Button
    $btnCopyLap.Location = New-Object System.Drawing.Point(385, 66)
    $btnCopyLap.Size = New-Object System.Drawing.Size(100, 26)
    $btnCopyLap.Text = "Salin ID"
    $btnCopyLap.Add_Click({
        if ($laptopId) { [System.Windows.Forms.Clipboard]::SetText($laptopId) }
        $btnCopyLap.Text = "Tersalin!"
    })
    $form.Controls.Add($btnCopyLap)

    # 2. Server ID
    if ($serverId) {
        $lblSrv = New-Object System.Windows.Forms.Label
        $lblSrv.Location = New-Object System.Drawing.Point(20, 108)
        $lblSrv.Size = New-Object System.Drawing.Size(465, 18)
        $sName = if ($serverName) { $serverName } else { "Server" }
        $lblSrv.Text = "Device ID Server ($sName):"
        $form.Controls.Add($lblSrv)

        $tSrv = New-Object System.Windows.Forms.TextBox
        $tSrv.Location = New-Object System.Drawing.Point(20, 128)
        $tSrv.Size = New-Object System.Drawing.Size(355, 24)
        $tSrv.Text = $serverId
        $tSrv.ReadOnly = $true
        $tSrv.Font = New-Object System.Drawing.Font("Consolas", 8)
        $form.Controls.Add($tSrv)

        $btnCopySrv = New-Object System.Windows.Forms.Button
        $btnCopySrv.Location = New-Object System.Drawing.Point(385, 126)
        $btnCopySrv.Size = New-Object System.Drawing.Size(100, 26)
        $btnCopySrv.Text = "Salin ID"
        $btnCopySrv.Add_Click({
            if ($serverId) { [System.Windows.Forms.Clipboard]::SetText($serverId) }
            $btnCopySrv.Text = "Tersalin!"
        })
        $form.Controls.Add($btnCopySrv)
    }

    $btnClose = New-Object System.Windows.Forms.Button
    $btnClose.Location = New-Object System.Drawing.Point(385, 200)
    $btnClose.Size = New-Object System.Drawing.Size(100, 30)
    $btnClose.Text = "Tutup"
    $btnClose.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Controls.Add($btnClose)

    $form.ShowDialog() | Out-Null
    $out = @{ status = "ok" }
    Write-Output ($out | ConvertTo-Json -Compress)
}

function Show-WakeOnLanConfigDialog {
    param($title, $serverName, $serverIp, $currentMac, $broadcastIp, $port)
    $form = New-Object System.Windows.Forms.Form
    $form.Text = if ($title) { $title } else { "Konfigurasi Wake on LAN" }
    $form.Size = New-Object System.Drawing.Size(560, 540)
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true

    # Header
    $headerTitle = New-Object System.Windows.Forms.Label
    $headerTitle.Location = New-Object System.Drawing.Point(20, 15)
    $headerTitle.Size = New-Object System.Drawing.Size(505, 24)
    $headerTitle.Text = "⚡ Wake on LAN (Menghidupkan Server Lewat Jaringan)"
    $headerTitle.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $form.Controls.Add($headerTitle)

    $headerSub = New-Object System.Windows.Forms.Label
    $headerSub.Location = New-Object System.Drawing.Point(22, 40)
    $headerSub.Size = New-Object System.Drawing.Size(505, 20)
    $sName = if ($serverName) { $serverName } else { "Server" }
    $headerSub.Text = "Pengaturan untuk menyalakan '$sName' dari kondisi mati/tidur (standby)."
    $headerSub.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $form.Controls.Add($headerSub)

    # Group 1: Hardware requirements & guidance
    $grpReq = New-Object System.Windows.Forms.GroupBox
    $grpReq.Location = New-Object System.Drawing.Point(20, 68)
    $grpReq.Size = New-Object System.Drawing.Size(505, 175)
    $grpReq.Text = "📌 Prasyarat & Panduan Setup Perangkat Keras (Hardware)"
    $grpReq.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)

    $tReq = New-Object System.Windows.Forms.TextBox
    $tReq.Location = New-Object System.Drawing.Point(15, 24)
    $tReq.Size = New-Object System.Drawing.Size(475, 138)
    $tReq.Multiline = $true
    $tReq.ReadOnly = $true
    $tReq.ScrollBars = "Vertical"
    $tReq.BackColor = [System.Drawing.SystemColors]::Window
    $tReq.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Regular)
    $guideLines = @(
        "1. Kabel LAN Fisik: Server wajib terhubung via kabel Ethernet RJ45 ke router/switch (WoL tidak bekerja via Wi-Fi pada kebanyakan PC).",
        "",
        "2. BIOS/UEFI Server: Aktifkan fitur 'Wake on LAN', 'Power On by PCIE', atau 'Enable Wake from S5/Standby' di menu Power BIOS/UEFI server.",
        "",
        "3. Daya Listrik Siaga: Power supply server harus tetap terhubung ke stopkontak listrik agar kartu LAN mendapatkan daya siaga (+5VSB).",
        "",
        "4. Jaringan Lokal: Laptop dan server harus berada dalam subnet/jaringan lokal yang sama untuk menerima broadcast Magic Packet UDP.",
        "",
        "Catatan: Anda dapat menyimpan konfigurasi sekarang. Begitu hardware server mendukung WoL, fitur ini langsung siap digunakan."
    )
    $tReq.Text = [string]::Join("`r`n", $guideLines)
    $grpReq.Controls.Add($tReq)
    $form.Controls.Add($grpReq)

    # Group 2: Connection settings
    $grpSet = New-Object System.Windows.Forms.GroupBox
    $grpSet.Location = New-Object System.Drawing.Point(20, 252)
    $grpSet.Size = New-Object System.Drawing.Size(505, 185)
    $grpSet.Text = "⚙️ Parameter Jaringan Wake on LAN"
    $grpSet.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)

    # MAC
    $lblMac = New-Object System.Windows.Forms.Label
    $lblMac.Location = New-Object System.Drawing.Point(15, 28)
    $lblMac.Size = New-Object System.Drawing.Size(475, 18)
    $lblMac.Text = "MAC Address Server (Alamat Fisik Kartu Jaringan):"
    $lblMac.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $grpSet.Controls.Add($lblMac)

    $tMac = New-Object System.Windows.Forms.TextBox
    $tMac.Location = New-Object System.Drawing.Point(15, 48)
    $tMac.Size = New-Object System.Drawing.Size(320, 24)
    $tMac.Text = if ($currentMac) { $currentMac } else { "" }
    $tMac.Font = New-Object System.Drawing.Font("Consolas", 9.5)
    $grpSet.Controls.Add($tMac)

    $btnDetect = New-Object System.Windows.Forms.Button
    $btnDetect.Location = New-Object System.Drawing.Point(345, 47)
    $btnDetect.Size = New-Object System.Drawing.Size(145, 26)
    $btnDetect.Text = "🔍 Deteksi Otomatis"
    $btnDetect.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
    $btnDetect.Add_Click({
        try {
            $btnDetect.Enabled = $false
            $btnDetect.Text = "Mencari ARP..."
            $form.Refresh()
            $targetIp = $serverIp
            if (-not $targetIp) {
                $targetIp = "zimaos.local"
            }
            try { Test-Connection -ComputerName $targetIp -Count 1 -Quiet -TimeoutSeconds 1 | Out-Null } catch {}
            $arpOut = arp -a
            $lines = $arpOut -split "`r?`n"
            $foundMac = ""
            foreach ($line in $lines) {
                if ($line -match "([0-9a-fA-F]{2}[:-]){5}([0-9a-fA-F]{2})") {
                    if ($targetIp -and $line.Contains($targetIp)) {
                        $foundMac = $matches[0]
                        break
                    }
                }
            }
            if ($foundMac) {
                $tMac.Text = $foundMac.Replace("-", ":").ToUpper()
                [System.Windows.Forms.MessageBox]::Show("MAC Address berhasil terdeteksi dari tabel ARP:`n$($tMac.Text)", "Deteksi Otomatis Berhasil", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
            } else {
                [System.Windows.Forms.MessageBox]::Show("Tidak dapat mendeteksi MAC Address untuk '$targetIp' secara otomatis.`n`nKemungkinan server sedang offline atau belum ada di tabel ARP lokal. Silakan masukkan MAC Address manual.", "Deteksi Otomatis", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
            }
        } catch {
            [System.Windows.Forms.MessageBox]::Show("Terjadi kesalahan saat memeriksa ARP: " + $_.Exception.Message, "Error", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        } finally {
            $btnDetect.Enabled = $true
            $btnDetect.Text = "🔍 Deteksi Otomatis"
        }
    })
    $grpSet.Controls.Add($btnDetect)

    # Broadcast IP
    $lblBcast = New-Object System.Windows.Forms.Label
    $lblBcast.Location = New-Object System.Drawing.Point(15, 82)
    $lblBcast.Size = New-Object System.Drawing.Size(475, 18)
    $lblBcast.Text = "Broadcast IP Address (Default: 255.255.255.255):"
    $lblBcast.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $grpSet.Controls.Add($lblBcast)

    $tBcast = New-Object System.Windows.Forms.TextBox
    $tBcast.Location = New-Object System.Drawing.Point(15, 102)
    $tBcast.Size = New-Object System.Drawing.Size(320, 24)
    $tBcast.Text = if ($broadcastIp) { $broadcastIp } else { "255.255.255.255" }
    $tBcast.Font = New-Object System.Drawing.Font("Consolas", 9.5)
    $grpSet.Controls.Add($tBcast)

    # Port
    $lblPort = New-Object System.Windows.Forms.Label
    $lblPort.Location = New-Object System.Drawing.Point(15, 134)
    $lblPort.Size = New-Object System.Drawing.Size(125, 18)
    $lblPort.Text = "Port UDP (Default: 9):"
    $lblPort.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
    $grpSet.Controls.Add($lblPort)

    $tPort = New-Object System.Windows.Forms.TextBox
    $tPort.Location = New-Object System.Drawing.Point(145, 131)
    $tPort.Size = New-Object System.Drawing.Size(100, 24)
    $tPort.Text = if ($port) { $port } else { "9" }
    $tPort.Font = New-Object System.Drawing.Font("Consolas", 9.5)
    $grpSet.Controls.Add($tPort)

    $form.Controls.Add($grpSet)

    # Bottom Buttons
    $btnTest = New-Object System.Windows.Forms.Button
    $btnTest.Location = New-Object System.Drawing.Point(20, 452)
    $btnTest.Size = New-Object System.Drawing.Size(195, 30)
    $btnTest.Text = "⚡ Kirim Paket Sekarang"
    $btnTest.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $btnTest.Add_Click({
        $m = $tMac.Text.Trim()
        $b = $tBcast.Text.Trim()
        $pStr = $tPort.Text.Trim()
        if (-not $m) {
            [System.Windows.Forms.MessageBox]::Show("Harap masukkan MAC Address terlebih dahulu sebelum menguji pengiriman.", "Wake on LAN", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
            return
        }
        $clean = $m -replace "[:-]", ""
        if ($clean.Length -ne 12 -or ($clean -notmatch "^[0-9A-Fa-f]{12}$")) {
            [System.Windows.Forms.MessageBox]::Show("Format MAC Address tidak valid. Harus terdiri dari 12 karakter heksadesimal (contoh: 00:11:22:33:44:55).", "Wake on LAN", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)
            return
        }
        $portNum = 9
        if ($pStr -match '^[0-9]+$') { $portNum = [int]$pStr }
        if (-not $b) { $b = "255.255.255.255" }
        
        try {
            $macBytes = [byte[]]@(0..5 | ForEach-Object { [System.Convert]::ToByte($clean.Substring($_ * 2, 2), 16) })
            $packetBytes = [byte[]]@(0..5 | ForEach-Object { 255 })
            for ($i = 0; $i -lt 16; $i++) {
                $packetBytes += $macBytes
            }
            $udp = New-Object System.Net.Sockets.UdpClient
            $udp.EnableBroadcast = $true
            $ep = New-Object System.Net.IPEndPoint([System.Net.IPAddress]::Parse($b), $portNum)
            for ($k = 0; $k -lt 3; $k++) {
                $udp.Send($packetBytes, $packetBytes.Length, $ep) | Out-Null
                [System.Threading.Thread]::Sleep(50)
            }
            $udp.Close()
            [System.Windows.Forms.MessageBox]::Show("Paket Magic (Wake on LAN) berhasil dikirim ke $($m) via $($b):$($portNum) (3x paket broadcast UDP).`n`nJika server mendukung WoL dan sudah diaktifkan di BIOS, server akan mulai menyala dalam beberapa saat.", "Pengiriman Berhasil", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Information)
        } catch {
            [System.Windows.Forms.MessageBox]::Show("Gagal mengirim paket Magic WoL:`n" + $_.Exception.Message, "Gagal Mengirim", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error)
        }
    })
    $form.Controls.Add($btnTest)

    $btnSave = New-Object System.Windows.Forms.Button
    $btnSave.Location = New-Object System.Drawing.Point(325, 452)
    $btnSave.Size = New-Object System.Drawing.Size(95, 30)
    $btnSave.Text = "Simpan"
    $btnSave.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $btnSave.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.AcceptButton = $btnSave
    $form.Controls.Add($btnSave)

    $btnCancel = New-Object System.Windows.Forms.Button
    $btnCancel.Location = New-Object System.Drawing.Point(430, 452)
    $btnCancel.Size = New-Object System.Drawing.Size(95, 30)
    $btnCancel.Text = "Batal"
    $btnCancel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
    $form.CancelButton = $btnCancel
    $form.Controls.Add($btnCancel)

    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
        $pClean = 9
        if ($tPort.Text.Trim() -match '^[0-9]+$') { $pClean = [int]$tPort.Text.Trim() }
        $out = @{
            status = "ok"
            mac_address = $tMac.Text.Trim().ToUpper()
            broadcast_ip = if ($tBcast.Text.Trim()) { $tBcast.Text.Trim() } else { "255.255.255.255" }
            port = $pClean
        }
        Write-Output ($out | ConvertTo-Json -Compress)
    } else {
        $out = @{ status = "cancel" }
        Write-Output ($out | ConvertTo-Json -Compress)
    }
}

if ($action -eq "one_input") { Show-OneInput $args[1] $args[2] $args[3] $args[4] }
elseif ($action -eq "two_inputs") { Show-TwoInputs $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] $args[7] }
elseif ($action -eq "three_inputs") { Show-ThreeInputs $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] $args[7] $args[8] }
elseif ($action -eq "choose_zip") { Show-ChooseZip $args[1] }
elseif ($action -eq "save_zip") { Show-SaveZip $args[1] $args[2] }
elseif ($action -eq "save_log") { Show-SaveLog $args[1] $args[2] }
elseif ($action -eq "choose_folder") { Show-ChooseFolder $args[1] }
elseif ($action -eq "create_task_dialog") { Show-CreateTaskDialog $args[1] $args[2] $args[3] $args[4] }
elseif ($action -eq "config_backup_dual_dialog") { Show-ConfigBackupDualDialog $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] $args[7] $args[8] }
elseif ($action -eq "account_setup") { Show-AccountSetup $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] $args[7] $args[8] }
elseif ($action -eq "setup_wizard") { Show-SetupWizard $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] $args[7] $args[8] $args[9] $args[10] $args[11] $args[12] }
elseif ($action -eq "add_device_dialog") { Show-AddDeviceDialog $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] }
elseif ($action -eq "pending_device_dialog") { Show-PendingDeviceDialog $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] }
elseif ($action -eq "my_device_id_dialog") { Show-MyDeviceIdDialog $args[1] $args[2] $args[3] $args[4] }
elseif ($action -eq "wake_on_lan_dialog") { Show-WakeOnLanConfigDialog $args[1] $args[2] $args[3] $args[4] $args[5] $args[6] }
# SIG # Begin signature block
# MIIF0wYJKoZIhvcNAQcCoIIFxDCCBcACAQExCzAJBgUrDgMCGgUAMGkGCisGAQQB
# gjcCAQSgWzBZMDQGCisGAQQBgjcCAR4wJgIDAQAABBAfzDtgWUsITrck0sYpfvNR
# AgEAAgEAAgEAAgEAAgEAMCEwCQYFKw4DAhoFAAQUa5HJ8cNhSnF983M7ncNI74CO
# FougggNMMIIDSDCCAjCgAwIBAgIQVGb09oekxrxD1s9OIbn4JjANBgkqhkiG9w0B
# AQsFADA8MRgwFgYDVQQKDA9BbGdpdGhhIFByb2plY3QxIDAeBgNVBAMMF0FsZ2l0
# aGEgUHJvamVjdCBEZXNrdG9wMB4XDTI2MTAyMzEzMjcyNloXDTMxMTAyMzEzMzcy
# NlowPDEYMBYGA1UECgwPQWxnaXRoYSBQcm9qZWN0MSAwHgYDVQQDDBdBbGdpdGhh
# IFByb2plY3QgRGVza3RvcDCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEB
# AMVQAffSVbTv8scTOUdyHwp2PGagTHPTWt4wbI+a7T4LVOKNYWgl0HnHdSeH4vA/
# sWsIfYrPeJjD1KDh0RzHfxxYdysn8UcXUjNYnxuq2zBF9iIYUn/PyBPnePrXeooI
# X8SLcWMOKXnvGEWMNA5NkXHKEjtZCL6eQSKBXP3j5MaLavbSghPcJc5ptBhgnNgW
# Bx2B8YWuHKAFKStKLMyzZUy6qce29RYY9+Eye+rDcmSBZP+edqvozO/E/v2n7cpa
# MCRJ7jwJzefvQ1weBcFg4xFudbn+xULYBkDbf6kfM/t3p0H6KNtS0rE42sjehHeh
# z5kGB0x2Oraqw1lkSK8xv90CAwEAAaNGMEQwDgYDVR0PAQH/BAQDAgeAMBMGA1Ud
# JQQMMAoGCCsGAQUFBwMDMB0GA1UdDgQWBBR3ibhnNyDf4drS3xVzqsIqNZnE2DAN
# BgkqhkiG9w0BAQsFAAOCAQEAb7dNrEuPs7z2TO8VPH1jOgK3yAnQFEd59hy/XZOV
# rEfrsirTz6zghBwkSNLGzaKz8IWQPx9jtNGYgETS/dnkFnaEB9uqf1JNFFFe45G3
# /oD1wSXTtSWyWHTDOeSaQvfpwJ1r0hBVu+Ygb/fbDR6z3f0trt6Tu7dKkdMRC/DP
# /6SIo8DV0p6/hD2m9KGo8ns3/SIpJ44o8yAytKR4VE4PaEcFqesjmFH+8cPYHr8Z
# 9MU8tQ3W6O1u134hf/coNt93nsPkKdbKTGN27DbIAvzorzxyqmvGSBYnjNxJaoeC
# O+wVzL2ydrv2bsnwx48oNROU2tPqbSzvy/gS73KI4bBtUDGCAfEwggHtAgEBMFAw
# PDEYMBYGA1UECgwPQWxnaXRoYSBQcm9qZWN0MSAwHgYDVQQDDBdBbGdpdGhhIFBy
# b2plY3QgRGVza3RvcAIQVGb09oekxrxD1s9OIbn4JjAJBgUrDgMCGgUAoHgwGAYK
# KwYBBAGCNwIBDDEKMAigAoAAoQKAADAZBgkqhkiG9w0BCQMxDAYKKwYBBAGCNwIB
# BDAcBgorBgEEAYI3AgELMQ4wDAYKKwYBBAGCNwIBFTAjBgkqhkiG9w0BCQQxFgQU
# 6q38UsKOiZsJ1Pi+ogN1NN95XgowDQYJKoZIhvcNAQEBBQAEggEAn2cCdBnh9OZ2
# D9wF/RIebW91Uhtm3JFGW5cM+6NyNDnybDdYcArxTSeuF17izrtylIj1msvDrAzZ
# Um31kNsZZHFInGcLxDAtZgTyuGI/iACrXY+uohLHU+2aQE6goCrEFNUPapOJh1vf
# vnFSRER0AGoY3tkqqNEbbEN5RPcPU4owyAI+x1/5JrH952jJHP/1Va8Uk1Ouej2Y
# EfNuKjHfn4ez8QelpFR8r3Pln7ipwcWYJ6KOZmXjK0zDr2u5IKle6oIsA2muh8t+
# vcq665KQZHV8Mzgm1slDZpO7l4nJxt0OXjIFQ7juGcmwpnXZ8jumA5hU9CVgDuxJ
# v9++kPcQfA==
# SIG # End signature block
