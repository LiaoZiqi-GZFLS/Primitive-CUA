# WeChat Moments (朋友圈) Workflow

## Summary
Navigate and interact with WeChat Moments (朋友圈) in the WeChat Windows desktop client — browse posts, like, comment, and view profiles.

## Context
WeChat desktop client has a dedicated Moments view accessible from the left sidebar or
shortcut menu. The interface uses custom-drawn UI, making template-based automation the
primary approach. UIA may not expose Moments-specific elements reliably.

## Guidance

### Accessing Moments
- In the left sidebar, click the "朋友圈" (Moments) icon — it looks like a circular photo icon
- Alternative: Use the shortcut Ctrl+Alt+Z (if enabled) to open Moments directly
- The Moments window opens as a separate panel or overlay on the right side
- On first open, wait 2-3 seconds for content to load (network-dependent)

### Moments Layout
- **Top area**: Cover photo of the current user, with profile picture and name
- **Main feed**: Vertical scrollable list of posts from friends
- **Each post contains**:
  - Friend's avatar (left side) and name (top of post)
  - Text content (expandable if long — look for "全文" link)
  - Images grid (1-9 images in a tiled layout)
  - Timestamp and location tag below content
  - Action row: Like (心形) and Comment (评论) buttons
  - Existing likes and comments displayed below the action row
- **Right side**: May show trending or recommended content

### Common Operations

#### Browse Posts
```
1. Click 朋友圈 in left sidebar
2. Wait 2-3s for feed to load
3. Scroll down to browse — use scroll amount ~400 for comfortable reading
4. Use ocr to check which posts are visible on screen
```

#### Like a Post
```
1. Find the target post by OCR matching friend name or content text
2. Locate the 赞/like button (heart icon) below the post content
3. Click the button
4. Verify: the heart icon should change to filled/colored state
   OR the post should show your name in the likes list
```

#### Comment on a Post
```
1. Click the 评论/comment button below the post
2. A text input field appears — click into it
3. Type your comment text
4. Press Enter or click the send/submit button
5. Verify: your comment appears below the post
```

#### Post to Moments
```
1. Click the camera/post button (usually top-right area of Moments)
2. Choose text-only or image+text mode:
   - Text-only: directly type content into the editor
   - With images: first click add-image button, select images, then add text
3. Write your post content
4. Optionally set privacy: click the visibility selector (default "公开"/Public)
5. Click "发表" (Publish) button
6. Verify: post appears at the top of your feed
```

#### View a Friend's Profile
```
1. Click the friend's avatar or name in a post
2. This opens their profile page showing their Moments history
3. Use scroll to browse their past posts
4. Click back/close to return to the main feed
```

### Troubleshooting
- **Moments not loading**: Check network connection; Try closing and reopening the Moments panel
- **Images not loading**: Wait longer — WeChat lazy-loads images; Scroll past and back to trigger reload
- **Cannot find like/comment buttons**: Use magnifier on the bottom area of a post — buttons are small
- **Chinese IME**: If typing Chinese comments, switch IME to Chinese mode before typing; use type_keys for keyboard shortcuts, paste_text for content
- **Moments window overlapping**: Use focus_window("微信") first to ensure correct z-order
