import React, { useState, useEffect } from 'react';
import { useConfirmDialog } from '../../shared/ui/ConfirmDialog';

interface Holiday {
  id: number;
  holiday_name: string;
  holiday_date: string;
  is_custom: boolean;
  is_locked?: boolean;
}

interface HolidayConfiguratorProps {
  apiRequest: (path: string, init?: RequestInit) => Promise<any>;
}

export const HolidayConfigurator: React.FC<HolidayConfiguratorProps> = ({ apiRequest }) => {
  const confirm = useConfirmDialog();
  const [holidays, setHolidays] = useState<Holiday[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear());
  const [generating, setGenerating] = useState(false);
  
  const [name, setName] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const [editRowId, setEditRowId] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editDate, setEditDate] = useState('');
  const fetchHolidays = async () => {
    try {
      setLoading(true);
      const res = await apiRequest('/api/holidays');
      if (res.ok) {
        setHolidays(await res.json());
      }
    } catch (error) {
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHolidays();
  }, []);

  const handleGenerate = async () => {
    if (!await confirm({ title: 'Tạo lịch nghỉ Nhà nước', message: `Bạn có muốn tự động tạo lịch nghỉ Nhà nước cho năm ${selectedYear}? Các ngày đã có sẽ không bị ghi đè.`, confirmLabel: 'Tạo lịch' })) return;
    try {
      setGenerating(true);
      const res = await apiRequest(`/api/holidays/generate/${selectedYear}`, {
        method: 'POST'
      });
      if (res.ok) {
        const data = await res.json();
        alert(data.message);
        fetchHolidays();
      } else {
        const data = await res.json();
        alert(data.detail || 'Lỗi khi tạo lịch nghỉ');
      }
    } catch (error) {
      alert('Lỗi kết nối');
    } finally {
      setGenerating(false);
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!startDate || !endDate) return;
    if (new Date(startDate) > new Date(endDate)) {
        alert("Ngày kết thúc phải lớn hơn hoặc bằng ngày bắt đầu!");
        return;
    }
    try {
      const res = await apiRequest('/api/holidays/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          holiday_name: name,
          start_date: startDate,
          end_date: endDate,
          is_custom: true
        })
      });
      if (res.ok) {
        alert('Đã thêm ngày lễ/bù thành công và áp dụng cho toàn bộ nhân sự!');
        setName('');
        setStartDate('');
        setEndDate('');
        setShowForm(false);
        fetchHolidays();
      } else {
        const data = await res.json();
        alert(data.detail || 'Lỗi khi thêm ngày lễ');
      }
    } catch (error) {
      alert('Lỗi kết nối');
    }
  };

  const handleEditClick = (h: Holiday) => {
      setEditRowId(h.id);
      setEditName(h.holiday_name);
      setEditDate(h.holiday_date);
  };

  const handleEditCancel = () => {
      setEditRowId(null);
  };

  const handleEditSave = async (id: number) => {
      try {
        const res = await apiRequest(`/api/holidays/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                holiday_name: editName,
                holiday_date: editDate
            })
        });
        if (res.ok) {
            setEditRowId(null);
            fetchHolidays();
        } else {
            const data = await res.json();
            alert(data.detail || 'Lỗi khi cập nhật');
        }
      } catch (error) {
          alert('Lỗi kết nối');
      }
  };

  const handleDelete = async (id: number) => {
    const holiday = holidays.find(h => h.id === id);
    if (!holiday) return;

    let confirmMsg = 'Bạn có chắc chắn muốn xóa ngày lễ này không?';
    if (holiday.is_locked) {
      confirmMsg = 'Bạn có chắc chắn muốn xóa ngày lễ này không vì bảng công đã được chốt, xóa ngày lễ trên bảng danh sách ngày lễ nhưng ngày công bên dưới đã được áp dụng thì vẫn giữ nguyên không cần xóa?';
    } else {
      confirmMsg = 'Bạn có chắc chắn muốn xóa ngày lễ này không? Xóa ngày lễ trên bảng danh sách ngày lễ và xóa ngày công bên dưới đã được áp dụng.';
    }

    if (!await confirm({ title: 'Xóa ngày lễ', message: confirmMsg, confirmLabel: 'Xóa', tone: 'danger' })) return;

    try {
      const res = await apiRequest(`/api/holidays/${id}`, { method: 'DELETE' });
      if (res.ok) {
        fetchHolidays();
      }
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4 font-roboto border-l-4 border-blue-500">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-bold text-gray-800 flex items-center">
          <span className="text-xl mr-2">📅</span> Thiết lập Ngày lễ / Nghỉ bù
        </h3>
        <div className="flex items-center gap-3 holiday-toolbar-actions">
          <select 
            value={selectedYear} 
            onChange={e => setSelectedYear(Number(e.target.value))}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500 font-medium holiday-toolbar-control"
          >
            {[2023, 2024, 2025, 2026, 2027, 2028].map(y => (
              <option key={y} value={y}>Năm {y}</option>
            ))}
          </select>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white px-4 py-2 rounded-md font-medium transition text-sm flex items-center gap-1 holiday-toolbar-control"
          >
            {generating ? 'Đang tạo...' : `Tự động tạo (${selectedYear})`}
          </button>
          <button
            onClick={() => setShowForm(!showForm)}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md font-medium transition text-sm flex items-center holiday-toolbar-control"
          >
            {showForm ? 'Đóng' : 'Custom Nghỉ bù'}
          </button>
        </div>
      </div>

      {showForm && (
        <form onSubmit={handleAdd} className="mb-4 bg-gray-50 p-4 rounded-md border border-gray-200 grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          <div className="flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">Tên ngày lễ / bù</label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Nghỉ bù 30/4"
              className="w-full border-gray-300 rounded-md shadow-sm p-2 text-sm focus:ring-blue-500 focus:border-blue-500 border"
            />
          </div>
          <div className="flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">Từ ngày</label>
            <input
              type="date"
              required
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full border-gray-300 rounded-md shadow-sm p-2 text-sm focus:ring-blue-500 focus:border-blue-500 border"
            />
          </div>
          <div className="flex flex-col">
            <label className="block text-sm font-medium text-gray-700 mb-1">Đến ngày</label>
            <input
              type="date"
              required
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              min={startDate}
              className="w-full border-gray-300 rounded-md shadow-sm p-2 text-sm focus:ring-blue-500 focus:border-blue-500 border"
            />
          </div>
          <div>
            <button type="submit" className="w-full bg-blue-900 hover:bg-blue-800 text-white px-4 py-2 rounded-md font-medium transition text-sm h-10 flex items-center justify-center">
              Lưu & Áp dụng
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div className="text-sm text-gray-500">Đang tải...</div>
      ) : (
        <div className="overflow-auto max-h-[320px] border border-gray-200 rounded-md">
          {holidays.filter(h => h.holiday_date.startsWith(selectedYear.toString())).length === 0 ? (
            <div className="text-sm text-gray-400 italic py-4 px-4">Chưa có cấu hình ngày lễ nào trong năm {selectedYear}.</div>
          ) : (
            <table className="min-w-full divide-y divide-gray-200 table-fixed">
              <thead className="bg-gray-50 sticky top-0 z-10 shadow-[0_1px_0_rgba(229,231,235,1)]">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-16 bg-gray-50">STT</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-50">Tên ngày lễ / bù</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-48 bg-gray-50">Ngày áp dụng</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-32 bg-gray-50">Phân loại</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-32 bg-gray-50">Thao tác</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {holidays.filter(h => h.holiday_date.startsWith(selectedYear.toString())).map((h, idx) => (
                  <tr key={h.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{idx + 1}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {editRowId === h.id ? (
                        <input type="text" value={editName} onChange={e => setEditName(e.target.value)} className="border border-gray-300 rounded px-2 py-1 w-full" />
                      ) : (
                        h.holiday_name
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {editRowId === h.id ? (
                        <input type="date" value={editDate} onChange={e => setEditDate(e.target.value)} className="border border-gray-300 rounded px-2 py-1 w-full" />
                      ) : (
                        h.holiday_date
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${h.is_custom ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'}`}>
                        {h.is_custom ? 'Nghỉ bù' : 'Nhà nước'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      {editRowId === h.id ? (
                        <div className="flex justify-end gap-2">
                          <button onClick={() => handleEditSave(h.id)} className="text-green-600 hover:text-green-900 font-bold">Lưu</button>
                          <button onClick={handleEditCancel} className="text-gray-500 hover:text-gray-700">Hủy</button>
                        </div>
                      ) : (
                        <div className="flex justify-end gap-2">
                          <button onClick={() => handleEditClick(h)} className="text-indigo-600 hover:text-indigo-900 font-bold">Sửa</button>
                          <button onClick={() => handleDelete(h.id)} className="text-red-600 hover:text-red-900 font-bold">Xóa</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
};
