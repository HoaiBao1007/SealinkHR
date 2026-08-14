param(
    [string]$OutputPath = "D:\SEALINK WEB\docs\Huong_dan_su_dung_SEALINK_Ke_toan_truong.docx",
    [string]$QaPdfPath = "D:\SEALINK WEB\docs\_qa\Huong_dan_su_dung_SEALINK_Ke_toan_truong.pdf"
)

$ErrorActionPreference = 'Stop'

$wdCollapseEnd = 0
$wdPageBreak = 7
$wdAlignParagraphLeft = 0
$wdAlignParagraphCenter = 1
$wdAlignParagraphRight = 2
$wdAlignVerticalCenter = 1
$wdPreferredWidthPoints = 3
$wdStyleNormal = -1
$wdStyleHeading1 = -2
$wdStyleHeading2 = -3
$wdStyleHeading3 = -4
$wdSaveFormatDocx = 16
$wdExportFormatPdf = 17
$wdHeaderFooterPrimary = 1
$wdHeaderFooterFirstPage = 2
$wdFieldPage = 33
$wdFieldNumPages = 26
$wdLineStyleSingle = 1

function WdColor([string]$Hex) {
    $value = $Hex.TrimStart('#')
    $r = [Convert]::ToInt32($value.Substring(0, 2), 16)
    $g = [Convert]::ToInt32($value.Substring(2, 2), 16)
    $b = [Convert]::ToInt32($value.Substring(4, 2), 16)
    return $r + ($g * 256) + ($b * 65536)
}

$C = @{
    Blue = WdColor '#2E74B5'
    DarkBlue = WdColor '#1F4D78'
    Ink = WdColor '#0B2545'
    FillBlue = WdColor '#E8EEF5'
    LightGray = WdColor '#F2F4F7'
    Callout = WdColor '#F4F6F9'
    White = WdColor '#FFFFFF'
    Gold = WdColor '#7A5A00'
    GoldFill = WdColor '#FFF7D6'
    Red = WdColor '#9B1C1C'
    RedFill = WdColor '#FDECEC'
    Green = WdColor '#166534'
    GreenFill = WdColor '#ECFDF3'
    Gray = WdColor '#64748B'
    Border = WdColor '#D6DEE8'
}

$script:word = $null
$script:doc = $null

function End-Range {
    $r = $script:doc.Range($script:doc.Content.End - 1, $script:doc.Content.End - 1)
    $r.Collapse($wdCollapseEnd)
    return $r
}

function Add-Paragraph {
    param(
        [string]$Text,
        [int]$Style = $wdStyleNormal,
        [int]$Alignment = $wdAlignParagraphLeft,
        [double]$Before = 0,
        [double]$After = 6,
        [switch]$Bold,
        [switch]$Italic,
        [int]$Color = $C.Ink,
        [double]$FontSize = 11,
        [switch]$KeepWithNext
    )
    $start = $script:doc.Content.End - 1
    $r = $script:doc.Range($start, $start)
    $r.Text = $Text + "`r"
    $p = $script:doc.Range($start, $start + [Math]::Max(1, $Text.Length)).Paragraphs.First
    $p.Range.Style = $script:doc.Styles.Item($Style)
    $p.Alignment = $Alignment
    $p.Format.SpaceBefore = $Before
    $p.Format.SpaceAfter = $After
    $p.Format.LineSpacingRule = 5
    $p.Format.LineSpacing = 13.75
    $p.Format.KeepWithNext = [int]$KeepWithNext.IsPresent * -1
    $p.Range.Font.Name = 'Calibri'
    $p.Range.Font.Size = $FontSize
    $p.Range.Font.Bold = [int]$Bold.IsPresent * -1
    $p.Range.Font.Italic = [int]$Italic.IsPresent * -1
    $p.Range.Font.Color = $Color
    return $p
}

function Add-Heading {
    param([string]$Text, [ValidateSet(1,2,3)][int]$Level)
    $style = switch ($Level) { 1 { $wdStyleHeading1 } 2 { $wdStyleHeading2 } 3 { $wdStyleHeading3 } }
    $size = switch ($Level) { 1 { 16 } 2 { 13 } 3 { 12 } }
    $before = switch ($Level) { 1 { 18 } 2 { 14 } 3 { 10 } }
    $after = switch ($Level) { 1 { 10 } 2 { 7 } 3 { 5 } }
    $color = if ($Level -eq 3) { $C.DarkBlue } else { $C.Blue }
    return Add-Paragraph -Text $Text -Style $style -Before $before -After $after -Bold -Color $color -FontSize $size -KeepWithNext
}

function Add-PageBreak {
    $r = End-Range
    $r.InsertBreak($wdPageBreak)
}

function Add-List {
    param([string[]]$Items, [ValidateSet('bullet','number')][string]$Type = 'bullet')
    foreach ($item in $Items) {
        $p = Add-Paragraph -Text $item -After 4 -FontSize 11
        if ($Type -eq 'bullet') {
            $p.Range.ListFormat.ApplyBulletDefault()
        } else {
            $p.Range.ListFormat.ApplyNumberDefault()
        }
        $p.Format.LeftIndent = 27
        $p.Format.FirstLineIndent = -13.5
        $p.Format.SpaceAfter = 4
    }
}

function Set-CellText {
    param($Cell, [string]$Text, [switch]$Bold, [int]$Color = $C.Ink, [double]$Size = 9.5, [int]$Align = $wdAlignParagraphLeft)
    $Cell.Range.Text = $Text
    $Cell.Range.Font.Name = 'Calibri'
    $Cell.Range.Font.Size = $Size
    $Cell.Range.Font.Bold = [int]$Bold.IsPresent * -1
    $Cell.Range.Font.Color = $Color
    $Cell.Range.ParagraphFormat.Alignment = $Align
    $Cell.Range.ParagraphFormat.SpaceAfter = 0
    $Cell.Range.ParagraphFormat.SpaceBefore = 0
    $Cell.VerticalAlignment = $wdAlignVerticalCenter
}

function Add-Table {
    param(
        [string[]]$Headers,
        [object[]]$Rows,
        [double[]]$Widths,
        [double]$FontSize = 9.5
    )
    $range = End-Range
    $table = $script:doc.Tables.Add($range, $Rows.Count + 1, $Headers.Count)
    $table.AllowAutoFit = $false
    $table.PreferredWidthType = $wdPreferredWidthPoints
    $table.PreferredWidth = 468
    $table.Rows.Alignment = 0
    $table.LeftPadding = 6
    $table.RightPadding = 6
    $table.TopPadding = 4
    $table.BottomPadding = 4
    $table.Borders.Enable = 1
    $table.Borders.OutsideLineStyle = $wdLineStyleSingle
    $table.Borders.InsideLineStyle = $wdLineStyleSingle
    $table.Borders.OutsideColor = $C.Border
    $table.Borders.InsideColor = $C.Border
    for ($i = 1; $i -le $Headers.Count; $i++) {
        $table.Columns.Item($i).Width = $Widths[$i - 1]
        Set-CellText -Cell $table.Cell(1, $i) -Text $Headers[$i - 1] -Bold -Color $C.DarkBlue -Size $FontSize
        $table.Cell(1, $i).Range.Shading.BackgroundPatternColor = $C.FillBlue
    }
    $table.Rows.Item(1).HeadingFormat = -1
    for ($r = 0; $r -lt $Rows.Count; $r++) {
        $row = @($Rows[$r])
        for ($c = 0; $c -lt $Headers.Count; $c++) {
            $value = if ($c -lt $row.Count) { [string]$row[$c] } else { '' }
            $cell = $table.Cell($r + 2, $c + 1)
            Set-CellText -Cell $cell -Text $value -Size $FontSize
            # Word COM can intermittently return a null Shading object for body cells.
            # Keep table rows white; header shading and borders preserve readability.
        }
    }
    $after = End-Range
    $after.Text = "`r"
    $script:doc.Paragraphs.Last.Format.SpaceAfter = 4
    return $table
}

function Add-Callout {
    param(
        [string]$Title,
        [string]$Text,
        [ValidateSet('info','warning','risk','success')][string]$Tone = 'info'
    )
    $range = End-Range
    $table = $script:doc.Tables.Add($range, 1, 1)
    $table.AllowAutoFit = $false
    $table.PreferredWidthType = $wdPreferredWidthPoints
    $table.PreferredWidth = 468
    $table.Columns.Item(1).Width = 468
    $table.LeftPadding = 10
    $table.RightPadding = 10
    $table.TopPadding = 8
    $table.BottomPadding = 8
    $table.Borders.Enable = 1
    $table.Borders.OutsideLineStyle = $wdLineStyleSingle
    $table.Borders.InsideLineStyle = 0
    $table.Rows.AllowBreakAcrossPages = 0
    $fill = $C.Callout
    $color = $C.DarkBlue
    if ($Tone -eq 'warning') { $fill = $C.GoldFill; $color = $C.Gold }
    elseif ($Tone -eq 'risk') { $fill = $C.RedFill; $color = $C.Red }
    elseif ($Tone -eq 'success') { $fill = $C.GreenFill; $color = $C.Green }
    $table.Cell(1, 1).Shading.BackgroundPatternColor = $fill
    $table.Borders.OutsideColor = $color
    $table.Cell(1, 1).Range.Text = "$Title`r$Text"
    $table.Cell(1, 1).Range.Font.Name = 'Calibri'
    $table.Cell(1, 1).Range.Font.Size = 10.5
    $table.Cell(1, 1).Range.Font.Color = $C.Ink
    $table.Cell(1, 1).Range.Paragraphs.Item(1).Range.Font.Bold = -1
    $table.Cell(1, 1).Range.Paragraphs.Item(1).Range.Font.Color = $color
    $table.Cell(1, 1).Range.ParagraphFormat.SpaceAfter = 3
    $after = End-Range
    $after.Text = "`r"
    $script:doc.Paragraphs.Last.Format.SpaceAfter = 4
}

function Add-Checklist {
    param([string[]]$Items)
    foreach ($item in $Items) {
        Add-Paragraph -Text ("☐  " + $item) -After 4 -FontSize 10.5 | Out-Null
    }
}

function Add-Rule {
    param([int]$Color = $C.Blue, [double]$Width = 1.5)
    $p = Add-Paragraph -Text '' -After 8
    $p.Borders.Item(-3).LineStyle = $wdLineStyleSingle
    $p.Borders.Item(-3).LineWidth = $Width
    $p.Borders.Item(-3).Color = $Color
}

$outputDir = Split-Path -Parent $OutputPath
$qaDir = Split-Path -Parent $QaPdfPath
New-Item -ItemType Directory -Force -Path $outputDir, $qaDir | Out-Null
if (Test-Path $OutputPath) { Remove-Item -LiteralPath $OutputPath -Force }
if (Test-Path $QaPdfPath) { Remove-Item -LiteralPath $QaPdfPath -Force }

try {
    $script:word = New-Object -ComObject Word.Application
    $script:word.Visible = $false
    $script:word.DisplayAlerts = 0
    $script:doc = $script:word.Documents.Add()

    $section = $script:doc.Sections.Item(1)
    $section.PageSetup.PageWidth = 612
    $section.PageSetup.PageHeight = 792
    $section.PageSetup.TopMargin = 72
    $section.PageSetup.BottomMargin = 72
    $section.PageSetup.LeftMargin = 72
    $section.PageSetup.RightMargin = 72
    $section.PageSetup.HeaderDistance = 35.4
    $section.PageSetup.FooterDistance = 35.4
    $section.PageSetup.DifferentFirstPageHeaderFooter = -1

    $normal = $script:doc.Styles.Item($wdStyleNormal)
    $normal.Font.Name = 'Calibri'
    $normal.Font.Size = 11
    $normal.Font.Color = $C.Ink
    $normal.ParagraphFormat.SpaceBefore = 0
    $normal.ParagraphFormat.SpaceAfter = 6
    $normal.ParagraphFormat.LineSpacingRule = 5
    $normal.ParagraphFormat.LineSpacing = 13.75

    $h1 = $script:doc.Styles.Item($wdStyleHeading1)
    $h1.Font.Name = 'Calibri'
    $h1.Font.Size = 16
    $h1.Font.Bold = -1
    $h1.Font.Color = $C.Blue
    $h1.ParagraphFormat.SpaceBefore = 18
    $h1.ParagraphFormat.SpaceAfter = 10
    $h1.ParagraphFormat.KeepWithNext = -1

    $h2 = $script:doc.Styles.Item($wdStyleHeading2)
    $h2.Font.Name = 'Calibri'
    $h2.Font.Size = 13
    $h2.Font.Bold = -1
    $h2.Font.Color = $C.Blue
    $h2.ParagraphFormat.SpaceBefore = 14
    $h2.ParagraphFormat.SpaceAfter = 7
    $h2.ParagraphFormat.KeepWithNext = -1

    $h3 = $script:doc.Styles.Item($wdStyleHeading3)
    $h3.Font.Name = 'Calibri'
    $h3.Font.Size = 12
    $h3.Font.Bold = -1
    $h3.Font.Color = $C.DarkBlue
    $h3.ParagraphFormat.SpaceBefore = 10
    $h3.ParagraphFormat.SpaceAfter = 5
    $h3.ParagraphFormat.KeepWithNext = -1

    # Running header and footer (first page deliberately blank).
    $header = $section.Headers.Item($wdHeaderFooterPrimary).Range
    $header.Text = 'SEALINK INTERNATIONAL  ·  HƯỚNG DẪN KẾ TOÁN TRƯỞNG'
    $header.Font.Name = 'Calibri'
    $header.Font.Size = 8.5
    $header.Font.Bold = -1
    $header.Font.Color = $C.Gray
    $header.ParagraphFormat.Alignment = $wdAlignParagraphRight
    $header.ParagraphFormat.Borders.Item(-3).LineStyle = $wdLineStyleSingle
    $header.ParagraphFormat.Borders.Item(-3).Color = $C.Border

    $footer = $section.Footers.Item($wdHeaderFooterPrimary).Range
    $footer.Text = 'Phiên bản 1.0  ·  03/08/2026                                      Trang '
    $footer.Font.Name = 'Calibri'
    $footer.Font.Size = 8.5
    $footer.Font.Color = $C.Gray
    $footer.ParagraphFormat.Alignment = $wdAlignParagraphCenter
    $footer.Collapse($wdCollapseEnd)
    $section.Footers.Item($wdHeaderFooterPrimary).Range.Fields.Add($footer, $wdFieldPage) | Out-Null
    $footer = $section.Footers.Item($wdHeaderFooterPrimary).Range
    $footer.Collapse($wdCollapseEnd)
    $footer.InsertAfter(' / ')
    $footer.Collapse($wdCollapseEnd)
    $section.Footers.Item($wdHeaderFooterPrimary).Range.Fields.Add($footer, $wdFieldNumPages) | Out-Null

    # Cover — editorial_cover preset.
    Add-Paragraph -Text 'SEALINK INTERNATIONAL' -Alignment $wdAlignParagraphCenter -After 20 -Bold -Color $C.Blue -FontSize 12 | Out-Null
    $logoPath = 'D:\SEALINK WEB\frontend\src\assets\LOGO SEALINK.jpg'
    if (Test-Path $logoPath) {
        $r = End-Range
        $shape = $script:doc.InlineShapes.AddPicture($logoPath, $false, $true, $r)
        $shape.LockAspectRatio = -1
        $shape.Width = 105
        $shape.Range.ParagraphFormat.Alignment = $wdAlignParagraphCenter
        Add-Paragraph -Text '' -After 18 | Out-Null
    }
    Add-Rule -Color $C.Blue -Width 2
    Add-Paragraph -Text 'SỔ TAY SỬ DỤNG HỆ THỐNG' -Alignment $wdAlignParagraphCenter -Before 20 -After 10 -Bold -Color $C.DarkBlue -FontSize 15 | Out-Null
    Add-Paragraph -Text 'DÀNH CHO KẾ TOÁN TRƯỞNG' -Alignment $wdAlignParagraphCenter -After 14 -Bold -Color $C.Ink -FontSize 23 | Out-Null
    Add-Paragraph -Text 'Từ đăng nhập, chấm công, tính lương đến Commission và phát hành phiếu lương' -Alignment $wdAlignParagraphCenter -After 28 -Color $C.Gray -FontSize 12 | Out-Null
    Add-Callout -Title 'Mục tiêu của tài liệu' -Text 'Giúp người mới có thể tự vận hành theo đúng thứ tự, biết phải kiểm tra gì trước khi bấm xác nhận và biết dừng ở đâu khi số liệu chưa khớp.' -Tone info
    Add-Paragraph -Text 'Phạm vi: quyền Kế toán trưởng (ADMIN)' -Alignment $wdAlignParagraphCenter -Before 28 -After 4 -Bold -Color $C.DarkBlue -FontSize 10 | Out-Null
    Add-Paragraph -Text 'Phiên bản 1.0  ·  Cập nhật ngày 03/08/2026' -Alignment $wdAlignParagraphCenter -After 4 -Color $C.Gray -FontSize 9.5 | Out-Null
    Add-Paragraph -Text 'Tài liệu nội bộ — chỉ dùng trong SEALINK INTERNATIONAL' -Alignment $wdAlignParagraphCenter -After 0 -Italic -Color $C.Gray -FontSize 9 | Out-Null
    Add-PageBreak

    Add-Heading -Text 'Mục lục' -Level 1 | Out-Null
    Add-Paragraph -Text 'Có thể bấm trực tiếp vào tên mục trong Word để đi đến phần cần xem.' -After 10 -Italic -Color $C.Gray -FontSize 10 | Out-Null
    $tocRange = End-Range
    $script:doc.TablesOfContents.Add($tocRange, $true, 1, 3) | Out-Null
    $r = End-Range
    $r.Text = "`r"
    Add-PageBreak

    Add-Heading -Text 'Cách dùng sổ tay này' -Level 1 | Out-Null
    Add-Paragraph -Text 'Nếu bạn mới dùng hệ thống, hãy đi theo Chương 1 đến Chương 9. Nếu đang xử lý một việc cụ thể, mở mục lục và đến thẳng phần tương ứng. Các ô màu được dùng thống nhất trong toàn tài liệu:' | Out-Null
    Add-Table -Headers @('Màu / ký hiệu','Ý nghĩa') -Widths @(120,348) -Rows @(
        @('Màu xanh','Thông tin cần biết hoặc cách làm được khuyến nghị.'),
        @('Màu vàng','Chỗ cần dừng lại kiểm tra trước khi xác nhận.'),
        @('Màu đỏ','Thao tác có thể ảnh hưởng dữ liệu, tiền lương hoặc lịch sử.'),
        @('☐','Việc cần đánh dấu hoàn thành trong checklist.')
    ) | Out-Null
    Add-Callout -Title 'Nguyên tắc dễ nhớ' -Text 'Không sửa số chỉ để tổng nhìn “đẹp”. Hãy tìm đúng dữ liệu nguồn bị sai: hồ sơ nhân viên, ngày công, phụ cấp, file Commission hoặc trạng thái JOB.' -Tone warning

    Add-Heading -Text 'Phạm vi quyền của Kế toán trưởng' -Level 2 | Out-Null
    Add-Table -Headers @('Khu vực','Bạn có thể làm gì') -Widths @(135,333) -Rows @(
        @('Dashboard','Xem tổng quan nhân sự, công và tình trạng hệ thống.'),
        @('Nhân sự','Thêm, xem, sửa hồ sơ; cập nhật lương hợp đồng, phụ cấp và tài khoản.'),
        @('Phòng ban','Quản lý phòng ban, phân bổ nhân sự, cấu hình bonus và xem sơ đồ tổ chức.'),
        @('Bảng công','Upload, đối soát, chỉnh sửa, khóa, chốt và xuất bảng công.'),
        @('Xuất báo cáo','Xuất các báo cáo chấm công và nhân sự.'),
        @('Bảng lương','Tính lương, Commission, xuất ngân hàng, phát hành phiếu lương.'),
        @('Cá nhân','Xem phiếu lương và chấm công của chính mình.')
    ) | Out-Null
    Add-Callout -Title 'Không thuộc quyền Kế toán trưởng' -Text 'Backup dữ liệu và Nhật ký hệ thống là phần riêng của IT. Khi cần phục hồi dữ liệu hoặc tra cứu kỹ thuật, liên hệ người đang dùng quyền IT_ADMIN.' -Tone info

    Add-PageBreak
    Add-Heading -Text '1. Bản đồ công việc từ đầu tháng đến cuối tháng' -Level 1 | Out-Null
    Add-Paragraph -Text 'Đây là thứ tự nên làm trong một tháng lương. Làm đúng thứ tự sẽ giảm rất nhiều trường hợp bảng lương đúng một phần nhưng sai ở phần khác.' | Out-Null
    Add-Table -Headers @('Giai đoạn','Việc chính','Kết quả phải có') -Widths @(86,244,138) -Rows @(
        @('1. Chuẩn bị','Rà soát nhân viên mới, phòng ban, loại nhân viên, lương hợp đồng, tài khoản và mã máy chấm công.','Hồ sơ đủ để nhận diện đúng người.'),
        @('2. Chấm công','Đọc file vân tay, ghép file Notion, kiểm tra preview và lưu.','Dữ liệu công đủ từ ngày 23 đến ngày 22.'),
        @('3. Đối soát','Lọc bất thường, sửa ký hiệu có lý do, kiểm tra cuối tuần và đơn nghỉ.','Không còn lỗi chưa giải thích.'),
        @('4. Chốt công','Khóa bảng công, chốt và đồng bộ ngày công sang bảng lương.','Ngày công xuất hiện đúng ở tháng lương.'),
        @('5. Tính lương','Kiểm tra lương hợp đồng, phụ cấp, bảo hiểm, thuế, thưởng và Commission.','Tổng thu nhập, khấu trừ và thực nhận khớp.'),
        @('6. Thanh toán','Xuất báo cáo lương, file ngân hàng; xác nhận và phát hành phiếu lương.','Nhân viên xem được phiếu lương đúng tháng.'),
        @('7. Lưu hồ sơ','Lưu file đối soát, ghi chú phát sinh và không chỉnh lại tháng đã chốt nếu chưa có lý do.','Có dấu vết để kiểm tra lại sau này.')
    ) | Out-Null
    Add-Callout -Title 'Mốc thời gian cần nhớ' -Text 'Chu kỳ công của hệ thống là từ ngày 23 tháng trước đến ngày 22 tháng này. Tháng lương là tháng nhận kết quả của chu kỳ đó. Ví dụ: công 23/06–22/07 được dùng cho lương tháng 07/2026.' -Tone warning

    Add-Heading -Text 'Checklist mở đầu một tháng lương' -Level 2 | Out-Null
    Add-Checklist @(
        'Đã chọn đúng tháng lương ở đầu trang.',
        'Nhân viên mới đã có mã máy chấm công và tên tiếng Việt.',
        'Tên Notion đã được gắn đúng người nếu nhân viên có đơn nghỉ/WFH.',
        'Thay đổi loại nhân viên hoặc mức lương đã có tháng bắt đầu áp dụng.',
        'Phòng ban và cấu hình bonus đang dùng đúng tháng.'
    )

    Add-PageBreak
    Add-Heading -Text '2. Đăng nhập, thanh điều hướng và thông báo' -Level 1 | Out-Null
    Add-Heading -Text '2.1 Đăng nhập' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Mở địa chỉ website do công ty cung cấp.',
        'Nhập tên đăng nhập và mật khẩu của tài khoản Kế toán trưởng.',
        'Bấm Đăng nhập hệ thống.',
        'Kiểm tra góc trên bên phải phải hiển thị đúng tên và vai trò “Kế toán trưởng”.'
    )
    Add-Callout -Title 'Nếu bị đưa về màn hình đăng nhập' -Text 'Phiên làm việc có thể đã hết hạn. Đăng nhập lại rồi mở lại chức năng đang làm. Không bấm gửi nhiều lần khi chưa biết thao tác trước đã lưu hay chưa.' -Tone info

    Add-Heading -Text '2.2 Cách đọc giao diện' -Level 2 | Out-Null
    Add-Table -Headers @('Vị trí','Dùng để làm gì') -Widths @(125,343) -Rows @(
        @('Menu bên trái','Chuyển giữa Dashboard, Nhân sự, Phòng ban, Bảng công, Xuất báo cáo và Bảng lương.'),
        @('Tháng lương phía trên','Quyết định dữ liệu lương đang xem và đang sửa.'),
        @('Chuông thông báo','Nhắc việc mới: yêu cầu bonus, phát hành phiếu lương, thay đổi nhân sự hoặc bảng công.'),
        @('Dòng trạng thái phía dưới','Cho biết hệ thống vừa tải, lưu thành công hay đang có lỗi.'),
        @('Nút Làm mới','Tải lại dữ liệu từ máy chủ; dùng sau khi một người khác vừa cập nhật.')
    ) | Out-Null

    Add-Heading -Text '2.3 Xử lý thông báo' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Bấm biểu tượng chuông để mở danh sách thông báo.',
        'Đọc tiêu đề và thời điểm. Các thông báo chưa đọc có badge màu đỏ.',
        'Bấm vào thông báo. Hệ thống sẽ đưa đến đúng nhân viên, tháng lương hoặc JOB Commission cần xử lý.',
        'Làm xong việc rồi mới đánh dấu đã đọc để không bỏ sót.'
    )
    Add-Callout -Title 'Nếu thông báo mở sai chỗ' -Text 'Đừng thao tác trên dòng gần giống. Hãy quay về danh sách, tìm theo mã JOB hoặc tên nhân viên ghi trong thông báo rồi đối chiếu lại kỳ nguồn.' -Tone warning

    Add-PageBreak
    Add-Heading -Text '3. Dashboard — xem nhanh trước khi bắt đầu' -Level 1 | Out-Null
    Add-Paragraph -Text 'Dashboard dùng để nhìn tổng thể, không phải nơi sửa dữ liệu. Hãy tải KPI và chú ý những ngày có số vắng hoặc bất thường tăng cao.' | Out-Null
    Add-List -Type number -Items @(
        'Chọn khoảng ngày cần xem.',
        'Bấm Tải Dashboard KPI.',
        'Xem số nhân sự hoạt động, có mặt, vắng và bất thường.',
        'Nếu cần lưu báo cáo tổng hợp, dùng nút xuất KPI.',
        'Khi thấy số liệu lạ, chuyển sang Bảng công để tìm nguyên nhân theo từng nhân viên.'
    )
    Add-Callout -Title 'Không kết luận chỉ từ Dashboard' -Text 'Dashboard là số tổng hợp. Một ngày có nhiều bất thường có thể do chưa map mã máy, chưa ghép file Notion hoặc chưa lưu lần import cuối.' -Tone info

    Add-PageBreak
    Add-Heading -Text '4. Nhân sự — chuẩn bị đúng dữ liệu trước khi tính công và lương' -Level 1 | Out-Null
    Add-Heading -Text '4.1 Thêm nhân viên mới' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Vào Nhân sự và bấm Thêm nhân viên mới.',
        'Nhập ID máy chấm công và tên tiếng Việt. Đây là hai thông tin quan trọng nhất để nhận diện người.',
        'Chọn phòng ban, chức vụ, ngày bắt đầu và tên Notion nếu có.',
        'Nhập lương hợp đồng, loại nhân viên và các khoản cơm, điện thoại, xăng xe, khoản khác.',
        'Nhập thông tin ngân hàng, thuế, bảo hiểm và liên hệ nếu đã có.',
        'Tên đăng nhập và mật khẩu có thể để trống; bổ sung sau khi cần cấp tài khoản.',
        'Bấm lưu và tìm lại nhân viên trong Bảng hồ sơ nhân viên để chắc chắn đã tạo đúng.'
    )

    Add-Heading -Text '4.2 Chọn đúng loại nhân viên' -Level 2 | Out-Null
    Add-Table -Headers @('Loại nhân viên','Cách hệ thống xử lý mặc định') -Widths @(135,333) -Rows @(
        @('Chính thức','Có các khoản phụ cấp mặc định và áp dụng bảo hiểm/thuế theo cấu hình hiện tại.'),
        @('Thử việc','Phụ cấp mặc định để 0; không áp bảo hiểm như nhân viên chính thức; thuế theo quy tắc thử việc.'),
        @('Học việc','Phụ cấp mặc định để 0; cách xử lý tương tự nhóm học việc đang cấu hình trong hệ thống.')
    ) | Out-Null
    Add-Callout -Title 'Thay đổi loại nhân viên phải có tháng hiệu lực' -Text 'Khi chuyển Học việc → Thử việc hoặc Thử việc → Chính thức, chọn đúng ngày/tháng bắt đầu. Tháng cũ phải giữ nguyên lịch sử; tháng mới và các tháng sau mới nhận trạng thái/phụ cấp mới.' -Tone warning

    Add-Heading -Text '4.3 Sửa, cấp tài khoản và xóa nhân viên' -Level 2 | Out-Null
    Add-List -Items @(
        'Dùng Sửa hoặc mở Chi tiết nhân viên để bổ sung thông tin còn thiếu.',
        'Khi cấp tài khoản, nhập tên đăng nhập không trùng và mật khẩu đủ mạnh; tài khoản phải liên kết đúng hồ sơ nhân viên.',
        'Không đổi mã máy chấm công nếu chưa đối chiếu dữ liệu cũ.',
        'Không xóa nhân viên chỉ vì đã nghỉ việc. Ưu tiên đổi trạng thái và tháng nghỉ để giữ lịch sử công/lương.'
    )
    Add-Callout -Title 'Xóa là thao tác nhạy cảm' -Text 'Xóa hồ sơ có thể ảnh hưởng mapping công, tài khoản và dữ liệu liên quan. Chỉ xóa bản tạo nhầm hoặc bản trùng sau khi đã xác định rõ bản đúng.' -Tone risk

    Add-Heading -Text '4.4 Kiểm tra nhanh trước khi rời tab Nhân sự' -Level 2 | Out-Null
    Add-Checklist @(
        'Tên tiếng Việt đúng chính tả.',
        'Mã máy chấm công không trùng người khác.',
        'Tên Notion đúng với tên trong file Leave Request.',
        'Phòng ban và chức vụ đúng.',
        'Loại nhân viên và tháng hiệu lực đúng.',
        'Lương, phụ cấp và tài khoản ngân hàng đã được người có trách nhiệm xác nhận.'
    )

    Add-PageBreak
    Add-Heading -Text '5. Phòng ban và sơ đồ tổ chức' -Level 1 | Out-Null
    Add-Heading -Text '5.1 Danh sách phòng ban' -Level 2 | Out-Null
    Add-Paragraph -Text 'Tab Danh sách phòng ban cho biết trưởng phòng và các nhân viên đang thuộc từng đơn vị.' | Out-Null
    Add-List -Type number -Items @(
        'Bấm + Thêm phòng ban khi cần tạo đơn vị mới.',
        'Dùng Chỉnh sửa TT để đổi tên hoặc thông tin phòng ban.',
        'Dùng Quản lý nhân sự để gán hoặc bỏ gán nhân viên.',
        'Nếu nhân viên không còn thuộc phòng nào, họ sẽ nằm trong nhóm chưa phân phòng cho đến khi được gán lại.',
        'Bấm Thu gọn/Mở rộng để rà soát danh sách dài.'
    )

    Add-Heading -Text '5.2 Cấu hình Bonus' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Mở Cấu hình Bonus tại đúng phòng ban.',
        'Chọn tháng bắt đầu áp dụng.',
        'Kiểm tra các mốc hệ số và tỷ lệ bonus.',
        'Lưu thay đổi và quay lại Commission để kiểm tra kết quả kỳ tương ứng.'
    )
    Add-Callout -Title 'Không sửa hồi tố nếu không có quyết định' -Text 'Cấu hình bonus của tháng mới không được làm thay đổi kỳ đã chốt. Nếu cần sửa kỳ cũ, phải có căn cứ, ghi chú và đối soát lại toàn bộ Commission của kỳ đó.' -Tone risk

    Add-Heading -Text '5.3 Sơ đồ tổ chức' -Level 2 | Out-Null
    Add-Paragraph -Text 'Sơ đồ lấy trực tiếp từ hồ sơ và phòng ban. Có thể tìm nhân viên/phòng, phóng to, vừa màn hình, mở toàn màn hình và xuất PDF vector. Nếu một người không xuất hiện, quay lại kiểm tra họ đã có phòng ban chưa.' | Out-Null

    Add-PageBreak
    Add-Heading -Text '6. Bảng công — từ file máy chấm công đến dữ liệu đã chốt' -Level 1 | Out-Null
    Add-Heading -Text '6.1 Chuẩn bị file và khoảng ngày' -Level 2 | Out-Null
    Add-Checklist @(
        'File máy chấm công đúng kỳ cần xử lý.',
        'File Notion Leave Request ở dạng CSV nếu cần ghép đơn nghỉ/WFH.',
        'Khoảng ngày từ 23 tháng trước đến 22 tháng hiện tại.',
        'Nhân viên mới đã có mã máy chấm công và tên Notion.'
    )
    Add-Callout -Title 'Khoảng ngày phải theo dữ liệu thật trong file' -Text 'Sau khi đọc file, kiểm tra lại “Từ” và “Đến”. Nếu file ghi 23/05–22/06 thì màn hình cũng phải là khoảng đó. Không lưu khi ngày trên màn hình vẫn là kỳ cũ.' -Tone warning

    Add-Heading -Text '6.2 Ba bước upload' -Level 2 | Out-Null
    Add-Table -Headers @('Bước trên màn hình','Việc cần làm','Khi nào đi tiếp') -Widths @(105,235,128) -Rows @(
        @('1. Đọc file vân tay','Chọn file máy công, chọn đúng khoảng ngày rồi đọc preview.','Tên, mã máy, số ngày và mốc giờ hợp lý.'),
        @('2. Khớp đơn Notion','Chọn CSV Notion; hệ thống ghép theo tên và khoảng Thời gian trong file.','Đơn nghỉ/WFH vào đúng người, đúng ngày.'),
        @('3. Xác nhận & Lưu','Lưu dữ liệu đã kiểm tra vào hệ thống.','Có thông báo thành công và bảng công tải lại.')
    ) | Out-Null
    Add-Paragraph -Text 'Phần chi tiết preview mặc định có thể đang ẩn. Bấm Xem chi tiết khi cần kiểm tra từng nhân viên; không cần mở toàn bộ nếu dữ liệu tổng đã đúng.' | Out-Null

    Add-Heading -Text '6.3 Quy tắc Notion và cuối tuần' -Level 2 | Out-Null
    Add-List -Items @(
        'Đơn nghỉ có trạng thái khác “Từ chối/Rejected” được xem là đơn hợp lệ theo logic hiện tại.',
        'Work From Home (WFH) là làm việc tại nhà, không được đánh là vắng.',
        'Thứ Bảy và Chủ nhật mặc định để trống, dù có dữ liệu quẹt thẻ hoặc đơn Notion.',
        'Một nhân viên có nhiều mã/bảng quẹt thẻ phải được ghép chung vào đúng một hồ sơ trước khi tính.',
        'Tên tiếng Việt dùng để hiển thị và xuất Excel; tên Notion chỉ dùng để khớp đơn.'
    )

    Add-PageBreak
    Add-Heading -Text '6.4 Đọc ký hiệu bảng công' -Level 2 | Out-Null
    Add-Table -Headers @('Ký hiệu','Cách hiểu') -Widths @(90,378) -Rows @(
        @('X','Đi làm đủ ngày.'),
        @('P','Nghỉ phép cả ngày.'),
        @('Ro','Vắng không lý do / nghỉ không lương theo quy tắc hiện tại.'),
        @('CT','Công tác.'),
        @('X/P','Sáng làm, chiều nghỉ phép.'),
        @('P/X','Sáng nghỉ phép, chiều làm.'),
        @('P/Ro','Sáng nghỉ phép, chiều vắng.'),
        @('Ro/P','Sáng vắng, chiều nghỉ phép.'),
        @('T7 / CN','Cuối tuần; để trống trong kết quả công chuẩn.')
    ) | Out-Null

    Add-Heading -Text '6.5 Rà soát và chỉnh sửa' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Chọn tháng công và dùng bộ lọc theo nhân viên, phòng ban hoặc bất thường.',
        'Mở chi tiết nhân viên để xem ngày, giờ vào/ra và các mốc quẹt thẻ.',
        'Nếu ký hiệu sai, mở chỉnh sửa tại đúng ngày.',
        'Chọn ký hiệu mới, nhập giờ vào/ra nếu cần và ghi lý do rõ ràng.',
        'Lưu, tải lại và kiểm tra ô vừa sửa.',
        'Không sửa liên tiếp nhiều lần khi lần trước chưa hiện trong lịch sử.'
    )
    Add-Callout -Title 'Mọi chỉnh sửa đều cần lý do' -Text 'Lý do nên nói rõ việc gì xảy ra, ví dụ “Quên chấm công, xác nhận đi làm đủ ngày” hoặc “WFH theo đơn ngày 06/07”. Tránh ghi “test”, “sửa lại” hoặc để trống.' -Tone warning

    Add-Heading -Text '6.6 Khóa, chốt, xuất và xóa bảng công' -Level 2 | Out-Null
    Add-Table -Headers @('Nút','Tác dụng','Lưu ý') -Widths @(100,210,158) -Rows @(
        @('Khóa bảng công','Ngăn chỉnh sửa thêm cho tháng đang xem.','Chỉ khóa sau khi đã đối soát.'),
        @('Chốt bảng công','Đồng bộ ngày công sang bảng lương của tháng tương ứng.','Bắt buộc trước khi tính lương.'),
        @('Xuất Excel','Xuất bảng công hiện tại để lưu/đối soát.','Kiểm tra tên Việt và cuối tuần trống.'),
        @('Xóa bảng công','Xóa dữ liệu quẹt thẻ và chỉnh sửa của tháng.','Không hoàn tác; không dùng để sửa một nhân viên.')
    ) | Out-Null
    Add-Callout -Title 'Xóa bảng công chỉ dùng khi làm lại toàn kỳ thử nghiệm' -Text 'Nếu chỉ sai một nhân viên hoặc một ngày, hãy sửa đúng ô đó. Không xóa cả tháng vì sẽ mất dữ liệu của những người đang đúng.' -Tone risk

    Add-Heading -Text 'Checklist chốt bảng công' -Level 2 | Out-Null
    Add-Checklist @(
        'Đủ ngày từ 23 đến 22.',
        'Không còn nhân viên “Không tìm thấy hồ sơ”.',
        'Đơn nghỉ và WFH đã vào đúng người.',
        'Thứ Bảy, Chủ nhật để trống.',
        'Các lần sửa đều có lý do.',
        'Đã xuất file đối soát.',
        'Đã khóa và chốt đồng bộ sang Bảng lương.'
    )

    Add-PageBreak
    Add-Heading -Text '7. Xuất báo cáo' -Level 1 | Out-Null
    Add-Paragraph -Text 'Khu vực Xuất báo cáo dùng để lấy file phục vụ HR/kế toán từ dữ liệu đã lưu. Trước khi tải, chọn đúng tháng và bộ lọc.' | Out-Null
    Add-List -Type number -Items @(
        'Chọn khoảng ngày hoặc tháng báo cáo.',
        'Chọn phòng ban hoặc nhân viên nếu chỉ cần một phần dữ liệu.',
        'Bấm tải báo cáo phù hợp.',
        'Mở file ngay sau khi tải và kiểm tra tên sheet, khoảng ngày, số nhân viên, tên tiếng Việt và định dạng số công.',
        'Đặt tên file có tháng và ngày xuất để dễ tìm lại.'
    )
    Add-Callout -Title 'File xuất không phải nơi sửa nguồn' -Text 'Nếu Excel sai, quay lại sửa dữ liệu trên website rồi xuất lại. Không nên sửa riêng file Excel vì lần xuất tiếp theo sẽ lại lấy dữ liệu cũ trong hệ thống.' -Tone info

    Add-PageBreak
    Add-Heading -Text '8. Bảng lương — kiểm tra, chốt và phát hành' -Level 1 | Out-Null
    Add-Heading -Text '8.1 Chọn đúng tháng lương' -Level 2 | Out-Null
    Add-Paragraph -Text 'Ô Tháng lương ở đầu trang là lựa chọn chính. Mọi bảng và nút trong khu vực Bảng lương phải theo tháng này. Trước mỗi lần lưu, hãy nhìn lại tháng đang hiển thị.' | Out-Null

    Add-Heading -Text '8.2 Ba khu vực chính' -Level 2 | Out-Null
    Add-Table -Headers @('Khu vực','Dùng khi nào') -Widths @(155,313) -Rows @(
        @('Bảng tổng hợp (Admin Grid)','Xem và nhập biến động theo tháng; kiểm tra kết quả lương của toàn công ty.'),
        @('Lương hợp đồng gốc','Quản lý nền lương, loại nhân viên, người phụ thuộc, ngân hàng và phụ cấp gốc.'),
        @('Commission','Import Job PnL, tính thưởng Sales, quản lý ví và JOB đang giữ bonus.')
    ) | Out-Null

    Add-Heading -Text '8.3 Cách đọc Bảng tổng hợp' -Level 2 | Out-Null
    Add-List -Items @(
        'Khối A là nhân viên chính thức; Khối B là thử việc/học việc.',
        'Ngày công lấy từ bảng công đã chốt, nhưng vẫn phải đối chiếu.',
        'Ô nhập tay là khoản kế toán có thể chỉnh theo chứng từ.',
        'Ô công thức tự động do hệ thống tính; không nhập đè chỉ để khớp tổng.',
        'Lương thực tế, phụ cấp, bảo hiểm, thuế, công đoàn và thực nhận được tính theo dữ liệu của tháng đang chọn.',
        'Commission được lấy từ ví thưởng/lệnh chi trả của đúng nhân viên và đúng tháng.'
    )
    Add-Callout -Title 'Cách hiểu đơn giản về thực nhận' -Text 'Thực nhận = các khoản được hưởng trong tháng − các khoản phải trừ. Hệ thống tự tính; người dùng chịu trách nhiệm kiểm tra dữ liệu đầu vào và chứng từ.' -Tone info

    Add-PageBreak
    Add-Heading -Text '8.4 Quy trình tính lương từng bước' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Chọn đúng tháng lương.',
        'Kiểm tra số nhân viên ở khối Chính thức và Thử việc/Học việc.',
        'Đối chiếu ngày công với bảng công đã chốt.',
        'Kiểm tra lương hợp đồng và phụ cấp nền của từng người có thay đổi.',
        'Nhập các biến động được phép: phụ cấp, KPI, thu nhập khác, thưởng, khấu trừ hoặc khoản khác theo chứng từ.',
        'Mở Commission để kiểm tra thưởng Sales và các lịch chi trả theo JOB.',
        'Rà soát bảo hiểm, thuế, công đoàn và thực nhận.',
        'Bấm lưu thay đổi. Tải lại trang để chắc dữ liệu vẫn còn.',
        'Xuất Excel báo cáo lương và file Payment ngân hàng để đối chiếu chéo.',
        'Khóa và xác nhận bảng lương khi đã được duyệt.',
        'Phát hành phiếu lương để nhân viên xem.'
    )

    Add-Heading -Text '8.5 Hoàn tác, khóa và xác nhận' -Level 2 | Out-Null
    Add-Table -Headers @('Thao tác','Dùng khi nào','Điều cần nhớ') -Widths @(120,205,143) -Rows @(
        @('Hoàn tác thay đổi chưa lưu','Vừa gõ sai nhưng chưa lưu.','Quay về dữ liệu đã tải gần nhất.'),
        @('Hoàn tác lần lưu gần nhất','Đã lưu nhầm một lần.','Chỉ dùng ngay sau khi phát hiện; kiểm tra lại từng dòng.'),
        @('Khóa bảng lương','Không cho sửa thêm.','Khóa trước khi xác nhận cuối cùng.'),
        @('Xác nhận bảng lương','Đánh dấu tháng đã hoàn tất.','Không xác nhận khi còn số chưa giải thích.'),
        @('Thu hồi phiếu lương','Dừng hiển thị phiếu đã phát hành.','Chỉ dùng khi phiếu có sai sót cần sửa và phát hành lại.')
    ) | Out-Null

    Add-Heading -Text '8.6 Xuất file và phát hành phiếu lương' -Level 2 | Out-Null
    Add-List -Items @(
        'Tải Excel Báo cáo Lương: dùng để lưu hồ sơ và đối soát tổng.',
        'Xuất Payment Ngân Hàng: dùng để chuẩn bị file chuyển khoản; kiểm tra tài khoản, tên người nhận và số tiền.',
        'Phát hành phiếu lương: chỉ sau khi số thực nhận đã chốt. Nhân viên sẽ nhận thông báo và xem được phiếu cá nhân.',
        'Phiếu lương có thể tải PDF dạng chữ; chỉ chứa nội dung phiếu, còn danh sách JOB chưa đủ điều kiện chỉ xem trên website.'
    )
    Add-Callout -Title 'Ba lần kiểm tra trước khi phát hành' -Text '1) Tổng hệ thống. 2) File ngân hàng. 3) Một vài phiếu lương mẫu ở các nhóm khác nhau. Ba nơi phải cùng số.' -Tone success

    Add-Heading -Text '9. Commission, Ví thưởng và Phễu bonus' -Level 1 | Out-Null
    Add-Heading -Text '9.1 Hiểu đúng bốn lớp dữ liệu' -Level 2 | Out-Null
    Add-Table -Headers @('Lớp','Nói đơn giản') -Widths @(135,333) -Rows @(
        @('File Commission','Danh sách JOB và số liệu P&L lấy từ Climax.'),
        @('Kết quả công thức','Tổng thưởng quý và mức thưởng chuẩn theo tháng.'),
        @('Ví thưởng','Cho biết đã ghi nhận, đang giữ, khả dụng, đã chuyển, đã lập lịch và đã trả.'),
        @('Sổ cái','Lịch sử tiền vào/ra theo từng JOB; không sửa dòng cũ, chỉ thêm dòng mới hoặc dòng đảo chiều.')
    ) | Out-Null
    Add-Callout -Title 'Đừng nhân “Đang giữ” lên ba lần' -Text 'Đang giữ là số chung của cả quý. Ba tháng chi trả là cách phân bổ tổng thưởng quý. Khi đối soát, nhìn tổng quý và từng tháng do hệ thống phân bổ; không lấy số đang giữ nhân 3.' -Tone warning

    Add-Heading -Text '9.2 Import Commission từ đầu' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Vào Bảng lương → Commission.',
        'Kéo thả file Job PnL With Realize/Unrealize Detail hoặc bấm chọn file.',
        'Kiểm tra khoảng Job Date From/Till trong file, tên Sales Rep, số JOB và tổng Profit/Loss.',
        'Xem trước các JOB, nhất là Payment Received, Profit/Loss và tên Sales Rep.',
        'Bấm xác nhận lưu khi kỳ nguồn đã đúng.',
        'Kiểm tra dòng mới trong Lịch sử Import đã lưu.',
        'Bấm Đồng bộ ví thưởng và đối chiếu số tổng.'
    )
    Add-Callout -Title 'Kỳ nguồn phải được nhận diện đúng' -Text 'Nếu file ghi 01-Apr-2026 → 30-Jun-2026 mà lịch sử chỉ hiện “tháng 07”, hãy dừng. Không xử lý ví cho đến khi kỳ nguồn hiển thị đúng, vì tháng chi trả và quý sau sẽ bị xác định sai.' -Tone risk

    Add-Heading -Text '9.3 Lịch sử Import' -Level 2 | Out-Null
    Add-Paragraph -Text 'Mỗi dòng là một Sales Rep trong một kỳ nguồn. Bấm vào kỳ hoặc nút Ví thưởng để mở đúng ví của người đó; không cộng chung nhiều nhân viên hoặc nhiều kỳ.' | Out-Null
    Add-Table -Headers @('Cột','Dùng để kiểm tra') -Widths @(130,338) -Rows @(
        @('Kỳ','Khoảng ngày nguồn của JOB.'),
        @('Tên Sales Rep / JOBS','Đúng người và đúng số JOB.'),
        @('Tổng Profit/Loss','Tổng P&L nguồn.'),
        @('Target / Hệ số','Đầu vào của cấu hình bonus.'),
        @('Tổng thưởng','Tổng thưởng của quý/kỳ.'),
        @('Thưởng/tháng','Mức chuẩn phân bổ theo tháng.'),
        @('Sửa / Remark / Xóa','Chỉ dùng khi có lý do và đã hiểu ảnh hưởng tới ví.')
    ) | Out-Null

    Add-Heading -Text '9.4 Cách đọc Ví thưởng' -Level 2 | Out-Null
    Add-Table -Headers @('Cột','Ý nghĩa') -Widths @(145,323) -Rows @(
        @('Kỳ nguồn → ba tháng chi trả','Quý phát sinh và ba tháng dự kiến trả.'),
        @('Tổng thưởng quý','Tổng quyền hưởng theo công thức của kỳ nguồn.'),
        @('Thưởng chuẩn / tháng','Phần chuẩn của mỗi tháng trong lịch trả.'),
        @('Giữ (cả quý)','Bonus của JOB chưa đủ điều kiện hoặc giữ thủ công; chỉ tính một lần cho cả quý.'),
        @('Đã lập lịch','Tiền đã dành cho một tháng trả cụ thể.'),
        @('Đã chuyển kỳ sau','Tiền đã chuyển từ tháng nguồn sang tháng đích.'),
        @('Khả dụng','Phần còn có thể lập lịch/chi trả.'),
        @('Đã trả','Tiền đã hoàn tất chi trả.'),
        @('Thu hồi','Khoản cần bù trừ nếu số dư bị âm.')
    ) | Out-Null

    Add-Heading -Text '9.5 JOB có Payment Received = NO' -Level 2 | Out-Null
    Add-Paragraph -Text 'JOB vẫn nằm trong tổng thưởng quý nhưng phần bonus của JOB được giữ lại. Nhân viên có thể mở tab Bonus đang giữ và gửi yêu cầu kế toán kiểm tra.' | Out-Null
    Add-List -Type number -Items @(
        'Nhận thông báo yêu cầu chi trả từ nhân viên.',
        'Bấm thông báo để đến đúng JOB trong “JOB đang giữ bonus & hàng đợi kế toán”.',
        'Đối chiếu mã JOB, Sales Rep, khách hàng, kỳ nguồn và số đang giữ.',
        'Nếu chưa có bằng chứng khách hàng thanh toán, bấm Từ chối và ghi lý do.',
        'Nếu đã có bằng chứng, bấm Xác minh.',
        'Chọn phương án trả: chia đều ba tháng kỳ sau hoặc trả một lần trong một tháng kỳ sau.',
        'Nhập ghi chú nguồn tiền/lý do chi trả.',
        'Bấm Lập lệnh chi trả.',
        'Kiểm tra lịch chi trả, sổ cái và Bảng lương của tháng nhận.'
    )
    Add-Callout -Title 'Yêu cầu của nhân viên không tự mở tiền' -Text 'Gửi yêu cầu chỉ tạo việc cần kiểm tra. Chỉ khi Kế toán trưởng xác minh và lập lệnh thì tiền mới được chuyển khỏi trạng thái giữ và đưa vào lịch trả.' -Tone info

    Add-Heading -Text '9.6 Ví dụ dễ hiểu' -Level 2 | Out-Null
    Add-Paragraph -Text 'Một JOB của quý 04–06 đang giữ 300.000 đồng. Quý này vốn trả trong tháng 07, 08, 09. Đến tháng 08 khách hàng mới thanh toán:' | Out-Null
    Add-Table -Headers @('Phương án','Kết quả') -Widths @(165,303) -Rows @(
        @('Chia đều 3 tháng kỳ sau','Lập lịch 100.000 vào tháng 10, 100.000 vào tháng 11 và 100.000 vào tháng 12.'),
        @('Trả một lần','Chọn một tháng trong quý 10–12, ví dụ tháng 11; toàn bộ 300.000 được lập lịch vào tháng 11.')
    ) | Out-Null
    Add-Paragraph -Text 'Ghi chú kế toán nên ghi: “Bonus mở khóa từ JOB [mã JOB], khách hàng đã thanh toán ngày …”. Ghi chú này sẽ hiện trên phiếu lương để nhân viên hiểu khoản cộng thêm từ đâu.' -Italic -Color $C.Gray -FontSize 10 | Out-Null

    Add-Heading -Text '9.7 Chuyển bonus và lập lịch chi trả thủ công' -Level 2 | Out-Null
    Add-Table -Headers @('Chức năng','Dùng khi nào','Kết quả') -Widths @(130,185,153) -Rows @(
        @('Chuyển sang kỳ/quý sau','Muốn chuyển một phần bonus khả dụng từ tháng này sang tháng khác.','Giảm ở tháng nguồn, tăng ở tháng đích; chưa phải đã trả.'),
        @('Lập lịch chi trả','Muốn dành số khả dụng cho một tháng trả cụ thể.','Số đó chuyển sang “Đã lập lịch”.'),
        @('Chi trả lịch','Đợt trả đã thực hiện xong.','Lịch chuyển sang đã trả.'),
        @('Hủy lịch','Lịch chưa trả và cần thay đổi.','Tiền quay lại khả dụng.')
    ) | Out-Null
    Add-Callout -Title 'Hai ô này không thay thế quy trình JOB đang giữ' -Text 'JOB đang giữ tự động phải đi qua yêu cầu → xác minh → lập lệnh theo JOB. Chuyển bonus/lập lịch thủ công chỉ dùng cho phần đang khả dụng hoặc điều phối tháng trả.' -Tone warning

    Add-Heading -Text '9.8 Sổ cái, hoàn tác và khóa bảng bonus' -Level 2 | Out-Null
    Add-List -Items @(
        'Sổ cái cho biết thời điểm, JOB, giao dịch, số tiền, tháng đích và lý do.',
        'Không sửa lịch sử cũ. Hoàn tác tạo bút toán đảo chiều để vẫn truy ra được việc đã làm.',
        'Hoàn tác bước gần nhất chỉ dùng trước khi khoản đã chi trả.',
        'Khóa bảng bonus khi kỳ đã đối soát xong. Sau khi khóa, Payment Received, giữ thủ công, lịch chi trả và hoàn tác đều bị chặn.',
        'Muốn sửa kỳ đã khóa phải có quyết định và quy trình mở khóa phù hợp; không tìm cách vòng qua cảnh báo.'
    )

    Add-Heading -Text '9.9 Sửa hoặc xóa Commission' -Level 2 | Out-Null
    Add-Callout -Title 'Chỉ xóa đúng nhân viên trong đúng kỳ' -Text 'Nút xóa trên một dòng lịch sử phải làm sạch Commission và ví của Sales Rep đó trong kỳ được chọn, không được xóa các nhân viên khác. Luôn đọc lại tên người và kỳ trong hộp xác nhận.' -Tone risk
    Add-Checklist @(
        'Đã chọn đúng Sales Rep.',
        'Đã chọn đúng kỳ nguồn.',
        'Đã lưu bằng chứng/ghi chú vì sao cần xóa.',
        'Khoản đã trả hoặc đã lập lịch đã được kiểm tra ảnh hưởng.',
        'Sau khi xóa đã tải lại Lịch sử Import và Ví thưởng để xác nhận.'
    )

    Add-Heading -Text '10. Phiếu lương và chấm công của chính Kế toán trưởng' -Level 1 | Out-Null
    Add-Heading -Text '10.1 Phiếu lương của tôi' -Level 2 | Out-Null
    Add-List -Type number -Items @(
        'Mở Phiếu lương của tôi.',
        'Chọn tháng đã được phát hành.',
        'Kiểm tra lương, phụ cấp, khấu trừ, thực nhận và phần thưởng doanh số nếu có.',
        'Bấm Tải PDF để lưu phiếu lương dạng chữ có thể chọn/copy.',
        'Nếu thiếu tháng, kiểm tra tháng đó đã được phát hành hay chưa.'
    )
    Add-Heading -Text '10.2 Chấm công của tôi' -Level 2 | Out-Null
    Add-Paragraph -Text 'Màn hình gồm lưới ký hiệu cô đọng và lịch công chi tiết phía dưới. Chọn tháng rồi bấm Làm mới; có thể rê chuột hoặc bấm nút ba chấm để xem các mốc quẹt thẻ trong ngày.' | Out-Null

    Add-Heading -Text '11. Checklist chốt tháng lương' -Level 1 | Out-Null
    Add-Heading -Text '11.1 Trước khi khóa bảng lương' -Level 2 | Out-Null
    Add-Checklist @(
        'Bảng công đã chốt và ngày công đã sang đúng tháng lương.',
        'Số nhân viên chính thức/thử việc/học việc đúng.',
        'Các thay đổi lương và phụ cấp có tháng hiệu lực đúng.',
        'Tổng bảo hiểm, thuế và công đoàn đã đối soát.',
        'Commission đã đồng bộ ví; JOB đang giữ và lịch chi trả đã rà soát.',
        'Không còn số âm hoặc khoản thu hồi chưa giải thích.',
        'Excel báo cáo lương và file ngân hàng cùng số với website.'
    )
    Add-Heading -Text '11.2 Trước khi phát hành phiếu lương' -Level 2 | Out-Null
    Add-Checklist @(
        'Bảng lương đã khóa và xác nhận.',
        'Đã kiểm tra thử ít nhất một phiếu chính thức, một phiếu thử việc/học việc và một phiếu có Commission.',
        'Tên, mã nhân viên, tài khoản ngân hàng và thực nhận đúng.',
        'Ghi chú khoản bonus bổ sung nêu rõ JOB nguồn.',
        'Tháng phát hành đúng.',
        'Đã có người duyệt cuối theo quy trình nội bộ.'
    )
    Add-Heading -Text '11.3 Sau khi phát hành' -Level 2 | Out-Null
    Add-Checklist @(
        'Nhân viên nhận được thông báo.',
        'Phiếu lương mở và tải PDF được.',
        'Lưu file Excel lương, Payment ngân hàng và báo cáo công theo tháng.',
        'Ghi lại mọi phát sinh cần xử lý ở tháng sau.',
        'Không mở khóa/sửa tháng đã phát hành nếu chưa có lý do và phê duyệt.'
    )

    Add-PageBreak
    Add-Heading -Text '12. Lỗi thường gặp và cách xử lý an toàn' -Level 1 | Out-Null
    Add-Table -Headers @('Hiện tượng','Nguyên nhân thường gặp','Cách xử lý') -Widths @(145,150,173) -FontSize 9 -Rows @(
        @('Không nhận diện nhân viên','Sai/trùng mã máy hoặc hồ sơ chưa có.','Tìm hồ sơ theo tên Việt; sửa đúng mã máy; đọc lại preview trước khi lưu.'),
        @('Đơn Notion không vào bảng công','Tên Notion hoặc khoảng Thời gian không khớp.','Đối chiếu cột Thời gian và tên; chạy lại bước Khớp đơn Notion.'),
        @('WFH bị đánh vắng','File chưa được ghép hoặc loại đơn chưa nhận diện.','Kiểm tra dòng WFH, trạng thái không bị từ chối và ngày nằm trong kỳ.'),
        @('Ngày công không sang lương','Bảng công chưa chốt hoặc chọn sai tháng lương.','Chốt lại đúng chu kỳ 23–22; mở đúng tháng lương và làm mới.'),
        @('Phụ cấp mất ở tháng sau','Quyết định hiệu lực/tháng loại nhân viên chưa đúng.','Kiểm tra lịch sử thay đổi và tháng bắt đầu áp dụng.'),
        @('Commission không có dữ liệu','Ví chưa đồng bộ hoặc đang chọn sai Sales Rep/kỳ.','Bấm đúng dòng lịch sử, đồng bộ ví và mở đúng kỳ nguồn.'),
        @('Thông báo không đưa đến JOB','JOB đã bị xóa/đổi kỳ hoặc thông báo cũ.','Tìm theo mã JOB trong Lịch sử Import và kiểm tra sổ cái.'),
        @('Nút bị khóa','Bảng công/lương/bonus đã khóa hoặc đã xác nhận.','Đọc cảnh báo; chỉ mở khóa khi có phê duyệt.'),
        @('Bị 401/403','Phiên hết hạn hoặc tài khoản không có quyền.','Đăng nhập lại; nếu còn lỗi, ghi lại thời điểm và liên hệ IT.'),
        @('Bị 404','Không có dữ liệu cho tháng hoặc đối tượng đã bị xóa.','Kiểm tra tháng, trạng thái phát hành và lịch sử thay đổi.')
    ) | Out-Null
    Add-Callout -Title 'Khi báo IT hỗ trợ' -Text 'Gửi đủ: tài khoản đang dùng, màn hình, tháng/kỳ, mã nhân viên hoặc JOB, thời điểm xảy ra, ảnh thông báo lỗi và việc vừa làm trước đó. Không gửi mật khẩu.' -Tone info

    Add-PageBreak
    Add-Heading -Text '13. Những điều tuyệt đối tránh' -Level 1 | Out-Null
    Add-List -Items @(
        'Không dùng số tay để che một lỗi dữ liệu nguồn.',
        'Không xóa cả bảng công khi chỉ sai một người.',
        'Không xóa Commission khi chưa đọc tên Sales Rep và kỳ trong xác nhận.',
        'Không đổi Payment Received hoặc lập lệnh bonus khi chưa có bằng chứng thanh toán.',
        'Không phát hành phiếu lương trước khi đối chiếu file ngân hàng.',
        'Không sửa tháng cũ chỉ để các tháng mới “đẹp”.',
        'Không dùng chung tài khoản cá nhân và không chia sẻ mật khẩu.',
        'Không bỏ qua thông báo lỗi rồi bấm lưu nhiều lần.'
    )
    Add-Callout -Title 'Quy tắc dừng' -Text 'Nếu không giải thích được một con số liên quan đến tiền, hãy dừng ở bước kiểm tra. Chưa khóa, chưa xác nhận, chưa phát hành và chưa chi trả cho đến khi tìm được nguồn.' -Tone risk

    Add-Heading -Text '14. Bảng từ ngữ ngắn gọn' -Level 1 | Out-Null
    Add-Table -Headers @('Từ trên hệ thống','Hiểu đơn giản') -Widths @(155,313) -Rows @(
        @('Kỳ nguồn','Khoảng thời gian JOB phát sinh.'),
        @('Ba tháng chi trả','Ba tháng dự kiến nhận thưởng của kỳ nguồn.'),
        @('Payment Received','Khách hàng đã thanh toán hay chưa.'),
        @('Giữ tự động','Bonus JOB bị giữ vì Payment Received = NO.'),
        @('Giữ thủ công','Khoản kế toán khóa riêng theo JOB.'),
        @('Khả dụng','Số còn có thể lập lịch hoặc chi trả.'),
        @('Lập lịch','Dành tiền cho một tháng trả cụ thể.'),
        @('Sổ cái','Lịch sử mọi thay đổi tiền thưởng.'),
        @('Override','Sửa bảng công có ghi nhận trước/sau và lý do.'),
        @('Phát hành','Cho phép nhân viên xem phiếu lương.'),
        @('Thu hồi phiếu','Tạm dừng cho nhân viên xem để sửa và phát hành lại.'),
        @('Hoàn tác','Tạo bước đảo ngược thao tác gần nhất trong phạm vi được phép.')
    ) | Out-Null

    Add-Heading -Text '15. Trang ghi chú vận hành' -Level 1 | Out-Null
    Add-Paragraph -Text 'Tháng lương: ____________________      Người lập: ____________________      Ngày chốt: ____________________' -After 12 | Out-Null
    Add-Paragraph -Text 'Các phát sinh cần theo dõi:' -Bold -Color $C.DarkBlue | Out-Null
    1..8 | ForEach-Object { Add-Paragraph -Text ("$_. __________________________________________________________________________________") -After 8 -FontSize 10 | Out-Null }

    Add-Callout -Title 'Kết thúc quy trình' -Text 'Một tháng chỉ được xem là hoàn tất khi bảng công đã chốt, bảng lương đã đối soát, file ngân hàng đã kiểm tra, phiếu lương đã phát hành đúng tháng và mọi khoản Commission bất thường đều có ghi chú.' -Tone success

    foreach ($toc in $script:doc.TablesOfContents) { $toc.Update() }
    $script:doc.Fields.Update() | Out-Null
    $script:doc.SaveAs2($OutputPath, $wdSaveFormatDocx)
    $script:doc.ExportAsFixedFormat($QaPdfPath, $wdExportFormatPdf)
    Write-Output "DOCX=$OutputPath"
    Write-Output "PDF=$QaPdfPath"
}
finally {
    if ($script:doc) {
        $script:doc.Close($false)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($script:doc) | Out-Null
    }
    if ($script:word) {
        $script:word.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($script:word) | Out-Null
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}




