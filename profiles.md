# Visitor Profiles — Examples

Five ready-to-use profile configurations for the AI chatbot. Each profile includes the data structure the dashboard creates via `POST /api/dashboard/visitor-profiles`.

---

## 1. Student

```json
{
  "name": "Student",
  "description": "A current or prospective student asking about courses, admissions, campus life, fees, scholarships, or student resources.",
  "response_instructions": "Use a friendly, encouraging tone. Prioritize information about enrollment deadlines, course availability, campus facilities, and student support services. Keep explanations clear and avoid jargon. If they ask about costs, mention financial aid and scholarship options proactively.",
  "color": "#3B82F6",
  "enabled": true
}
```

**When it matches:** Visitor mentions courses, admission, exams, campus, fees, scholarships, hostel, timetable, or uses casual/student-like language about school life.

**How the bot changes:** Answers become more encouraging and student-focused. Proactively mentions deadlines, financial aid, and support resources instead of just answering the literal question.

---

## 2. Parent

```json
{
  "name": "Parent",
  "description": "A parent or guardian asking about their child's education, school safety, attendance, fees, pickup/drop-off, parent-teacher meetings, or child welfare.",
  "response_instructions": "Prioritize attendance policies, safety measures, fee structures, and pickup/drop-off logistics. Keep tone reassuring and professional. Address concerns about child wellbeing directly and empathetically. Provide specific contact information for reaching the school office or counselor when relevant.",
  "color": "#10B981",
  "enabled": true
}
```

**When it matches:** Visitor uses phrases like "my child", "my son/daughter", asks about safety, attendance, school hours, parent meetings, or expresses concern about their kid's experience.

**How the bot changes:** Shifts to a reassuring, parent-concern-oriented tone. Proactively offers contact info for counselors and emphasizes safety and welfare policies.

---

## 3. Teacher

```json
{
  "name": "Teacher",
  "description": "A teacher or faculty member asking about curriculum, lesson planning, staff resources, professional development, grading policies, or school administrative procedures.",
  "response_instructions": "Use a professional, collegial tone. Prioritize curriculum standards, teaching resources, professional development opportunities, and staff-only policies. Reference internal tools and staff portals when relevant. Be concise — teachers are busy. For policy questions, point to the staff handbook or admin office.",
  "color": "#8B5CF6",
  "enabled": true
}
```

**When it matches:** Visitor discusses curriculum, lesson plans, grading rubrics, staff meetings, PD workshops, classroom resources, or uses professional/educator terminology.

**How the bot changes:** Answers become more concise and professional. References staff-specific resources, internal portals, and the staff handbook instead of general public info.

---

## 4. Corporate Client

```json
{
  "name": "Corporate Client",
  "description": "A business representative, HR manager, or corporate partner asking about bulk enrollment, institutional partnerships, training programs, group discounts, or B2B services.",
  "response_instructions": "Use a formal, business-oriented tone. Prioritize partnership opportunities, bulk pricing, institutional packages, and ROI-focused language. Offer to connect them with the business development team. Mention case studies, testimonials from similar organizations, and custom solutions. Avoid casual language.",
  "color": "#F59E0B",
  "enabled": true
}
```

**When it matches:** Visitor mentions bulk enrollment, partnerships, corporate training, group discounts, institutional pricing, or asks about B2B/enterprise solutions.

**How the bot changes:** Tone becomes formal and sales-oriented. Proactively mentions partnership tiers, bulk pricing, and offers direct connection to the business development team.

---

## 5. Alumni

```json
{
  "name": "Alumni",
  "description": "A former student or graduate asking about alumni network, transcript requests, diploma verification, career services, mentorship opportunities, or giving back to the institution.",
  "response_instructions": "Use a warm, nostalgic tone that acknowledges their connection to the school. Prioritize alumni network events, transcript/diploma request procedures, career services available to graduates, and mentorship or donation opportunities. Make them feel valued as part of the school's legacy.",
  "color": "#EC4899",
  "enabled": true
}
```

**When it matches:** Visitor mentions being a former student, alumni, graduating class, transcript requests, or asks about staying connected after leaving.

**How the bot changes:** Tone becomes warmer and more personal. Proactively mentions alumni events, career services for graduates, and ways to stay connected or give back.

---

## Frontend Data Mapping

The dashboard editor (`VisitorProfiles.tsx`) maps these fields as follows:

| Profile Field | UI Element | Type | Required |
|---|---|---|---|
| `name` | Name input | text | Yes |
| `description` | Description textarea | textarea | Yes |
| `response_instructions` | Response Instructions textarea (with tooltip) | textarea | No |
| `color` | Color picker | color picker | Yes |
| `enabled` | Enabled toggle | toggle switch | Yes |

### API Request Shape

```typescript
// POST /api/dashboard/visitor-profiles
// PUT /api/dashboard/visitor-profiles/{profile_id}
{
  name: string;
  description: string;
  response_instructions?: string | null;
  color: string;       // hex, e.g. "#3B82F6"
  enabled: boolean;
}
```

### API Response Shape

```typescript
// GET /api/dashboard/visitor-profiles
{
  id: string;
  tenant_id: string;
  name: string;
  description: string;
  response_instructions: string | null;
  color: string;
  enabled: boolean;
  created_at: string;  // ISO date
  updated_at: string;  // ISO date
}
```
