# AWS S3 Integration Setup Guide

This guide walks you through setting up real AWS S3 functionality for the MultiCam Controller.

## Step 1: Add AWS SDK Swift Package

### In Xcode:
1. Open `multiCamControllerMacos.xcodeproj`
2. Select your project in the navigator (top level)
3. Select the `multiCamControllerMacos` target
4. Go to **Package Dependencies** tab
5. Click **+** (Add Package Dependency)
6. Enter URL: `https://github.com/awslabs/aws-sdk-swift`
7. Click **Add Package**
8. **Select only AWSS3** from the package products list
9. Click **Add Package**

## Step 2: Enable Real S3 Code

### In `Services/S3Manager.swift`:
1. **Uncomment the imports** at the top:
   ```swift
   import AWSS3
   import AWSClientRuntime
   import ClientRuntime
   ```

2. **Uncomment the client property**:
   ```swift
   private var s3Client: S3Client?
   ```

3. **Uncomment the initialization**:
   ```swift
   Task {
       await configureAWSClient()
   }
   ```

4. **Replace the placeholder `uploadFiles` method** with the real implementation (uncomment the large commented block)

5. **Uncomment the real `configureAWSClient()` and `testConnection()` methods**

## Step 3: Configure AWS Credentials

You have several options for AWS credentials:

### Option A: AWS Credentials File (Recommended)
Create `~/.aws/credentials`:
```ini
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
```

Create `~/.aws/config`:
```ini
[default]
region = us-east-1
```

### Option B: Environment Variables
Set these in your shell or in Xcode's scheme:
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

### Option C: IAM Roles (if running on EC2)
The SDK will automatically use instance metadata if available.

## Step 4: Update S3 Bucket Name

In `Models/AppState.swift`, update the bucket name to match your S3 bucket:
```swift
let s3BucketName = "your-actual-bucket-name"
```

## Step 5: Set Up S3 Bucket

Ensure your S3 bucket exists and you have proper permissions:

### Required S3 Permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:PutObject",
                "s3:PutObjectAcl",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:HeadBucket"
            ],
            "Resource": [
                "arn:aws:s3:::your-bucket-name",
                "arn:aws:s3:::your-bucket-name/*"
            ]
        }
    ]
}
```

## Step 6: Test Configuration

### Add Test Button (Optional)
You can add a test button to your UI to verify S3 connectivity:

```swift
Button("Test S3 Connection") {
    Task {
        let success = await s3Manager.testConnection()
        print("S3 Connection: \(success ? "✅ Success" : "❌ Failed")")
    }
}
```

## Step 7: Build and Test

1. Build the project (`⌘B`)
2. Run the app
3. Record a video
4. Check the console for S3 upload logs
5. Verify files appear in your S3 bucket

## Expected File Structure in S3

Files will be uploaded with this structure:
```
your-bucket/
├── 2025-09-25/
│   └── 21-44-30/
│       ├── video_1234567890.mov
│       └── video_1234567891.mov
└── 2025-09-26/
    └── 15-23-45/
        └── video_1234567892.mov
```

## Troubleshooting

### Build Errors
- Ensure you selected **only AWSS3** package (not all packages)
- Clean build folder: Product → Clean Build Folder

### Authentication Errors
- Check AWS credentials are properly configured
- Verify AWS CLI works: `aws s3 ls s3://your-bucket-name`
- Check IAM permissions

### Upload Errors
- Verify bucket name matches exactly
- Check bucket region matches your configuration
- Ensure bucket exists and is accessible

### Common Issues
- **"No such bucket"**: Check bucket name and region
- **"Access Denied"**: Check IAM permissions
- **"Invalid credentials"**: Verify AWS credentials setup

## Security Notes

- Never commit AWS credentials to version control
- Use IAM roles with minimal required permissions
- Consider using temporary credentials for production
- Enable S3 bucket versioning and logging

## Performance Tips

- Consider multipart uploads for large files (>100MB)
- Use S3 Transfer Acceleration for global uploads
- Implement retry logic for failed uploads
- Consider parallel uploads for multiple files

---

Once configured, the app will upload all recorded videos to your S3 bucket automatically after each recording session!