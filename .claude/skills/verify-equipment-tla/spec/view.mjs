// View for the /statechart skill: chart states as a lab manager sees the equipment.
const STATUS = { available: "可用", needs_check: "待检查", repair: "维修或停用" };

export const title = "设备状态与预约（并发请求）";

export const state = (v) => {
  let label = STATUS[v.eStatus];
  if (v.flagged) label += "，异常未处理";
  if (Object.values(v.bookedWhileFlagged).some(Boolean)) label += "，期间建了使用预约";
  return label;
};

export const group = (v) => (v.flagged ? "异常未处理" : "正常");
export const colors = { 异常未处理: "orange", 正常: "teal" };

export const step = (action, from, to) => {
  switch (action) {
    case "ReportCommit":
      return to.flagged && !from.flagged ? "学生登记异常，提交" : null;
    case "EditCommit":
      return "管理员保存设备编辑";
    case "CreateCommit":
      return "有人建的预约提交";
    default:
      return null;
  }
};
