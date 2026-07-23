# Boss Zhipin (Boss直聘) Web Workflow

## Summary
Browser-based workflow for Boss Zhipin (zhipin.com) — login, browse jobs, filter results, communicate with recruiters, and manage applications.

## Context
Boss Zhipin is a major Chinese recruitment platform where job seekers chat directly with
recruiters/HR. The web version (zhipin.com) is a SPA with dynamic content loading.
Use web tools (web_navigate, web_click, web_type, web_get_content) as the primary
interaction method. The site requires login — plan for human-assisted login if needed.

## Guidance

### Login
```
1. Navigate to https://www.zhipin.com/web/geek/job
2. Wait 2-3s for page to fully render
3. If not logged in, a login dialog or page redirect appears
4. Two login methods:
   a. QR code scan: Show QR code to user via screenshot; user scans with Boss Zhipin app
   b. SMS verification: Enter phone number → get code → enter code
5. Use request_human_help() if login requires manual intervention
6. After login, verify: page should show job listings or user dashboard
```

### Key Pages and URLs
| Page | URL Pattern | Purpose |
|------|------------|---------|
| Job search | `/web/geek/job` | Browse and filter job listings |
| Chat/Messages | `/web/geek/chat` | Communicate with recruiters |
| Job detail | `/web/geek/job_detail/` + ID | View full job description |
| Company page | `/web/geek/company/` + ID | View company profiles |
| Profile/Resume | `/web/geek/resume` | Manage your online resume |
| Application status | `/web/geek/delivery` | Track submitted applications |
| Interview schedule | `/web/geek/interview` | View upcoming interviews |

### Job Search and Filtering
```
1. Navigate to https://www.zhipin.com/web/geek/job
2. Wait for job list to load — check web_content for "职位" or "岗位"
3. Set search filters:
   a. City/location: click the city selector (usually top of page), choose city
   b. Job type/role: use the search box to type a job title
   c. Salary range: click salary filter, select range
   d. Experience level: click experience filter
   e. Education level: click education filter
   f. Industry/field: click industry filter
4. Click "搜索" or press Enter to apply filters
5. Results update dynamically — wait 1-2s between filter changes
```

### Browsing Job Listings
```
1. After filtering, the job list appears as cards/sections
2. Each job card typically shows:
   - Job title (职位名称)
   - Salary range (e.g., "15K-25K")
   - Company name
   - Location (city/district)
   - Required experience and education
   - Recruiter/HR name and title
   - "立即沟通" (Chat Now) button
3. Scroll down to load more jobs (infinite scroll)
4. Use web_scroll 500 for incremental loading
```

### Viewing Job Details
```
1. Click a job title or card to open detail page
2. Detail page shows:
   - Full job description and requirements
   - Company information (size, industry, stage)
   - Work address on map
   - Company photos and office environment
   - "立即沟通" or "投递简历" buttons
3. Use web_content to extract the full job description
4. Return to list via browser back button or clicking the search breadcrumb
```

### Communicating with Recruiters
```
1. Click "立即沟通" (Chat Now) on a job card or detail page
2. A chat panel opens (may be a popup or new page section)
3. First message: usually an auto-greeting from the recruiter, OR
   you need to send your greeting first
4. Type message in the chat input box at the bottom
5. Press Enter or click send button
6. Chat history loads above — use web_scroll to view older messages
7. Key chat actions:
   - Send text: type and Enter
   - Send resume: click attachment/resume button (paperclip icon)
   - Request phone interview: ask directly in chat
8. Verify message sent: your message should appear in the chat history
```

### Managing Applications
```
1. Navigate to delivery/applications page
2. View list of applied jobs with status:
   - "已投递" (Delivered/Submitted)
   - "已查看" (Viewed by recruiter)
   - "沟通中" (In communication)
   - "面试邀约" (Interview invitation)
   - "不合适" (Not suitable — rejected)
3. Click on any application to open the chat with that recruiter
```

### Anti-Detection Notes
- Boss Zhipin may have rate limiting — space out actions by 1-2 seconds
- Avoid rapid clicking/refreshing — can trigger CAPTCHA
- If CAPTCHA appears, use request_human_help()
- The site uses dynamic rendering — always verify with web_content that elements loaded
- Some pages lazy-load via JavaScript scroll — use web_scroll before web_content

### Troubleshooting
- **Page not loading**: Wait 3-5s for JS to render; use web_refresh and try again
- **Login expired**: Look for login redirect or error messages in web_content
- **Chat button not working**: The "立即沟通" button may be conditionally visible based on job status
- **Filter not applying**: Some filters require clicking "确认/确定" button to apply
- **Infinite scroll stuck**: Scroll in smaller increments (200-300px) to trigger lazy loading
- **Company page blank**: Some company pages require being logged in to view
